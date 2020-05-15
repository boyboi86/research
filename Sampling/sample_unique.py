import pandas as pd
import numpy as np


from research.Util.multiprocess import mp_pandas_obj

p = print

# Estimating uniqueness of a label [4.1]
def _num_co_events(dataIndex: pd.DatetimeIndex, t1: pd.Series, molecule):
    '''
    Compute the number of concurrent events per bar.
    +molecule[0] is the date of the first event on which the weight will be computed
    +molecule[-1] is the date of the last event on which the weight will be computed
    Any event that starts before t1[modelcule].max() impacts the count.
    
    params: dataIndex => datetime Index based on co_event data input
    params: t1 => vert_bar t1, use in conjunction with tri_bar to generate t1
    params: molecule => multiprocessing
    '''
    #1) find events that span the period [molecule[0],molecule[-1]]
    t1=t1.fillna(dataIndex[-1]) # unclosed events still must impact other weights
    t1=t1[t1>=molecule[0]] # events that end at or after molecule[0]
    t1=t1.loc[:t1[molecule].max()] # events that start at or before t1[molecule].max()
    #2) count events spanning a bar
    iloc=dataIndex.searchsorted(pd.DatetimeIndex([t1.index[0],t1.max()]))
    count=pd.Series(0,index=dataIndex[iloc[0]:iloc[1]+1])
    for tIn,tOut in t1.iteritems():
        count.loc[tIn:tOut]+=1.
    return count.loc[molecule[0]:t1[molecule].max()]

# =======================================================
# Estimating the average uniqueness of a label [4.2]
def _mp_sample_TW(t1: pd.DatetimeIndex, num_conc_events: int, molecule):
    '''
    params: t1 => vert_bar end period
    params: num_conc_events => number of cocurrent events generated from _num_co_events,
                               This is an input not a func.
    params: molecule => multiprocess
    '''
    # Derive avg. uniqueness over the events lifespan
    wght=pd.Series(0.0, index = molecule) # NaNs no val index only
    for tIn,tOut in t1.loc[wght.index].iteritems():
        wght.loc[tIn]=(1./ num_conc_events.loc[tIn:tOut]).mean()
    
    return wght

def co_events(data: pd.Series, events: pd.DataFrame, num_threads: int):
    '''
    params: data => ORIGINAL close price series from imported data src
    params: events => this is used in conjunction to vert_bar function or tri_bar.
                      require pandas series with datetime value to check concurrent samples.
    optional
    params: num_threads => number of process to spawn for multiprocessing, default is 1. Pls do not change.
    
    t1 is the end of period dor vert_bar func, 
    where t0 which is the beginning period based on filter criteria will become vert_bar index.
    '''
    if isinstance(data, pd.Series):   
        if isinstance(data.dtype, (str, dict, tuple, list)):
            raise ValueError('data input must be pandas Series with dtype either float or integer value i.e. close price series')
        if data.isnull().values.any():
            raise ValueError('data series contain isinf, NaNs')
            
    if isinstance(data, pd.DataFrame):
        if isinstance(data.squeeze().dtype, (str, dict, tuple, list)):
            raise ValueError('data input must be pandas Series with dtype either float or integer value i.e. close price series')
        elif not isinstance(data.squeeze(), pd.Series):
            raise ValueError('data input must be pandas Series i.e. close price series')
        else:
            data = data.squeeze()
    else:
        raise ValueError('data input must be pandas Series with dtype either float or integer value i.e. close price series')
        
    if isinstance(events, pd.DataFrame):
        if isinstance(events, (int, str, float, dict, tuple, list)):
            raise ValueError('data input must be pandas DatetimeIndex or datetime values')
        if events.isnull().values.any():
            raise ValueError('events series contain isinf, NaNs, NaTs')
        if events.index.dtype != 'datetime64[ns]' or events['t1'].dtype != 'datetime64[ns]':
            raise ValueError('event["t1"] or devents.index is not datetime value')
    else:
        raise ValueError('data input must be pandas DateFrame please use tri_bar func provided')
    
        
    if isinstance(num_threads, (str, float, dict, tuple, list, pd.Series, np.ndarray)):
        raise ValueError('data input must be integer i.e. 1')

    out = pd.DataFrame()
    df0=mp_pandas_obj(func = _num_co_events, 
                      pd_obj=('molecule', events.index), 
                      num_threads = num_threads,
                      dataIndex = data.index,
                      t1 = events['t1'])
    df0 = df0.loc[~df0.index.duplicated(keep='last')]
    df0 = df0.reindex(df0.index).fillna(0)
    out['tW'] = mp_pandas_obj(_mp_sample_TW, ('molecule', events.index),
                              num_threads = num_threads,
                              t1=events['t1'],
                              num_conc_events=df0)
    return out
'''
# =======================================================
# Sequential Bootstrap [4.5.2]
## Build Indicator Matrix [4.3]
def getIndMatrix(barIx,t1):
    # Get Indicator matrix
    indM=(pd.DataFrame(0,index=barIx,columns=range(t1.shape[0])))
    for i,(t0,t1) in enumerate(t1.iteritems()):indM.loc[t0:t1,i]=1.
    return indM
# =======================================================
# Compute average uniqueness [4.4]
def getAvgUniqueness(indM):
    # Average uniqueness from indicator matrix
    c=indM.sum(axis=1) # concurrency
    u=indM.div(c,axis=0) # uniqueness
    avgU=u[u>0].mean() # avg. uniqueness
    return avgU
# =======================================================
# return sample from sequential bootstrap [4.5]
def seqBootstrap(indM,sLength=None):
    # Generate a sample via sequential bootstrap
    if sLength is None:sLength=indM.shape[1]
    phi=[]
    while len(phi)<sLength:
        avgU=pd.Series()
        for i in indM:
            indM_=indM[phi+[i]] # reduce indM
            avgU.loc[i]=getAvgUniqueness(indM_).iloc[-1]
        prob=avgU/avgU.sum() # draw prob
        phi+=[np.random.choice(indM.columns,p=prob)]
    return phi
# =======================================================
# Determination of sample weight by absolute return attribution [4.10]
def mpSampleW(t1,numCoEvents,close,molecule):
    # Derive sample weight by return attribution
    ret=np.log(close).diff() # log-returns, so that they are additive
    wght=pd.Series(index=molecule)
    for tIn,tOut in t1.loc[wght.index].iteritems():
        wght.loc[tIn]=(ret.loc[tIn:tOut]/numCoEvents.loc[tIn:tOut]).sum()
    return wght.abs()

# ============================================================


def _apply_weight_by_return(label_endtime, num_conc_events, close_series, molecule):
    """
    Snippet 4.10, page 69, Determination of Sample Weight by Absolute Return Attribution
    Derives sample weights based on concurrency and return. Works on a set of
    datetime index values (molecule). This allows the program to parallelize the processing.

    :param label_endtime: (pd.Series) Label endtime series (t1 for triple barrier events)
    :param num_conc_events: (pd.Series) number of concurrent labels (output from num_concurrent_events function).
    :param close_series: (pd.Series) close prices
    :param molecule: (an array) a set of datetime index values for processing.
    :return: (pd.Series) of sample weights based on number return and concurrency for molecule
    """

    ret = np.log(close_series).diff()  # Log-returns, so that they are additive
    weights = pd.Series(index=molecule)

    for t_in, t_out in label_endtime.loc[weights.index].iteritems():
        # Weights depend on returns and label concurrency
        weights.loc[t_in] = (ret.loc[t_in:t_out] / num_conc_events.loc[t_in:t_out]).sum()
    return weights.abs()


def get_weights_by_return(triple_barrier_events, close_series, num_threads=5):
    """
    Snippet 4.10(part 2), page 69, Determination of Sample Weight by Absolute Return Attribution
    This function is orchestrator for generating sample weights based on return using mp_pandas_obj.

    :param triple_barrier_events: (data frame) of events from labeling.get_events()
    :param close_series: (pd.Series) close prices
    :param num_threads: (int) the number of threads concurrently used by the function.
    :return: (pd.Series) of sample weights based on number return and concurrency
    """

    null_events = bool(triple_barrier_events.isnull().values.any())
    null_index = bool(triple_barrier_events.index.isnull().any())
    if null_events is False and null_index is False:
        try:
            num_conc_events = mp_pandas_obj(num_concurrent_events, ('molecule', triple_barrier_events.index), num_threads,
                                            close_series_index=close_series.index, label_endtime=triple_barrier_events['t1'])
            num_conc_events = num_conc_events.loc[~num_conc_events.index.duplicated(keep='last')]
            num_conc_events = num_conc_events.reindex(close_series.index).fillna(0)
            weights = mp_pandas_obj(_apply_weight_by_return, ('molecule', triple_barrier_events.index), num_threads,
                                    label_endtime=triple_barrier_events['t1'], num_conc_events=num_conc_events,
                                    close_series=close_series)
            weights *= weights.shape[0] / weights.sum()
            return weights
        except:
            p('NaN values in triple_barrier_events, delete NaNs')


def get_weights_by_time_decay(triple_barrier_events, close_series, num_threads=5, decay=1):
    """
    Snippet 4.11, page 70, Implementation of Time Decay Factors

    :param triple_barrier_events: (data frame) of events from labeling.get_events()
    :param close_series: (pd.Series) close prices
    :param num_threads: (int) the number of threads concurrently used by the function.
    :param decay: (int) decay factor
        - decay = 1 means there is no time decay
        - 0 < decay < 1 means that weights decay linearly over time, but every observation still receives a strictly positive weight, regadless of how old
        - decay = 0 means that weights converge linearly to zero, as they become older
        - decay < 0 means that the oldes portion c of the observations receive zero weight (i.e they are erased from memory)
    :return: (pd.Series) of sample weights based on time decay factors
    """
    null_events = bool(triple_barrier_events.isnull().values.any())
    null_index = bool(triple_barrier_events.index.isnull().any())
    if null_events is False and null_index is False:
        try:
            # Apply piecewise-linear decay to observed uniqueness
            # Newest observation gets weight=1, oldest observation gets weight=decay
            av_uniqueness = get_av_uniqueness_from_triple_barrier(triple_barrier_events, close_series, num_threads)
            decay_w = av_uniqueness['tW'].sort_index().cumsum()
            if decay >= 0:
                slope = (1 - decay) / decay_w.iloc[-1]
            else:
                slope = 1 / ((decay + 1) * decay_w.iloc[-1])
            const = 1 - slope * decay_w.iloc[-1]
            decay_w = const + slope * decay_w
            decay_w[decay_w < 0] = 0  # Weights can't be negative
            return decay_w
        else:
            p('NaN values in triple_barrier_events, delete NaNs')
'''