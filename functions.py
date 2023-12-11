# import package
import pandas as pd
import seaborn as sns
import numpy as np
import tensorflow as tf
import mysql.connector as mysql
import plotly.graph_objects as go

import math
import datetime
import requests
import io
import base64

import matplotlib.pylab as plt

## Function to collect data
def collect_forecast_pax_bms(today):
    yesterday = today - datetime.timedelta(days=1)
    yesterday = yesterday.strftime('%Y-%m-%d')

    yesterday_min_7 = today - datetime.timedelta(days=8)
    yesterday_min_7 = yesterday_min_7.strftime('%Y-%m-%d')

    # enter your server IP address/domain name
    HOST = "XX.XXX.XXX.XXX" # or "domain.com"
    # database name, if you want just to connect to MySQL server, leave it empty
    DATABASE = "DATABASE"
    # this is the user you create
    USER = "USER"
    # user password
    PASSWORD = "password"
    # connect to MySQL server
    db_connection = mysql.connect(host=HOST, database=DATABASE, user=USER, password=PASSWORD)
    print("Connected to:", db_connection.get_server_info())
    # enter your code here!

    # create a cursor object
    cursor = db_connection.cursor()

    # execute a SELECT query
    query = f"""
    SELECT id_seq, booking_id, route_info, price, shelter_id, created_by, created_on
    FROM t_trx_booking_detail AS tb 
    WHERE DATE(tb.created_on)<='{yesterday}' AND DATE(tb.created_on)>='{yesterday_min_7}'
    """

    cursor.execute(query)
    result_set = cursor.fetchall()    
    print(f"status: collecting data pax bms from {yesterday_min_7} to {yesterday}")

    column_names = [column[0] for column in cursor.description]

    df = pd.DataFrame()
    created_on = []
    shelter_id = []

    idx_created_on = column_names.index('created_on')
    idx_shelter_id = column_names.index('shelter_id')
    # process the data
    for row in result_set:
        created_on.append(row[idx_created_on])
        shelter_id.append(row[idx_shelter_id])

    shelter_name = []
    for i in range(len(shelter_id)):
        if shelter_id[i] == 1:
            shelter_name.append('T1')
        elif shelter_id[i] == 4:
            shelter_name.append('T2')
        elif shelter_id[i] == 5:
            shelter_name.append('T3')


    df['created_on'] = created_on
    df['shelter_name'] = shelter_name
    
    start = datetime.datetime(int(yesterday_min_7[:4]), int(yesterday_min_7[5:7]), int(yesterday_min_7[8:10]))
    end = datetime.datetime(int(yesterday[:4]), int(yesterday[5:7]), int(yesterday[8:10]), 23)
    step = datetime.timedelta(hours=1)

    date = []

    while start <= end:
        date.append(start.strftime('%Y-%m-%d %H:%M:%S'))
        start += step
    date = pd.to_datetime(pd.Series(date), format='%Y-%m-%d %H:%M:%S')

    date_time = []
    for i in range(len(date[:])):
        date_time.append(date[i].strftime("%Y-%m-%d %H:%M:%S"))
    
    pax_bms_t1 = get_pax_bms(df=df, date_time=date_time, terminal=1)
    pax_bms_t2 = get_pax_bms(df=df, date_time=date_time, terminal=2)
    pax_bms_t3 = get_pax_bms(df=df, date_time=date_time, terminal=3)

    data_bms = pd.DataFrame()
    data_bms.index= pd.to_datetime(date_time[:-1], errors = 'coerce')
    data_bms["PAX_BMS_T1"] = pax_bms_t1
    data_bms["PAX_BMS_T2"] = pax_bms_t2
    data_bms["PAX_BMS_T3"] = pax_bms_t3

    paxData = data_bms.values
    paxData_scaled = normalize_series(paxData)

    n_lookback = 24  # length of input sequences (lookback period)
    n_forecast = 24  # length of output sequences (forecast period)

    model = tf.keras.models.load_model('BiGRU-ModelAll.h5')
    print(f"status: starting forecasting data {today}")
    forecast_data = model_forecast(model, paxData_scaled, n_lookback, 1)
    print(f"status: success forecasting data {today}\n")
    forecast_data = forecast_data[:-1, 0]

    original = inverse_normalize_series(forecast_data, paxData)

    corrected_forecast = []
    for i in original:
        temp = []
        for j in i:
            if j < 0:
                temp.append(0)
            elif j >= 0:
                _temp = np.ceil(j)
                temp.append(int(_temp))        
        corrected_forecast.append(temp)


    corrected_forecast = np.array(corrected_forecast)
    corrected_forecast


    return corrected_forecast

## Generating data using forecast data
def generate_data(today, forecast, terminal):
    start = datetime.datetime(int(today[:4]), int(today[5:7]), int(today[8:]))
    end = datetime.datetime(int(today[:4]), int(today[5:7]), int(today[8:]), 23, 0, 0)
    step = datetime.timedelta(hours=1)

    date = []

    while start <= end:
        date.append(start.strftime('%Y-%m-%d %H:%M:%S'))
        start += step
    date = pd.to_datetime(pd.Series(date), format='%Y-%m-%d %H:%M:%S')

    hours = []
    for i in range(len(date[:])):
        hours.append(date[i].strftime("%H:%M"))

    data = pd.DataFrame({
        'TIME': hours
    })

    i = 0
    if terminal == 1:
        i = 0
    elif terminal == 2:
        i = 1
    elif terminal == 3:
        i = 2
    data['FORECAST_PAX_BMS'] = forecast[-24:,i]
    
    x = data[6:]['TIME']
    y = data[6:]['FORECAST_PAX_BMS']

    mean = data['FORECAST_PAX_BMS'].mean()
    err = math.sqrt(np.var(data['FORECAST_PAX_BMS']))

    mean_plus = mean + err
    mean_min = mean - err

    list_ovtime = data['TIME'][data['FORECAST_PAX_BMS'] > (mean_plus)].values

    ## Get first and last Time for FORECAST_PAX_BMS > mean
    time_ = []
    res = data[data['FORECAST_PAX_BMS'] > mean]
    time_.append(res['TIME'].values[0])
    time_.append(res['TIME'].values[-1])

    ## Create list of Dictionary
    dictData = []
    for j in range(len(data['TIME'].values)):
        D = {'TIME': data['TIME'][j],             
            'PRAKIRAAN PAX BMS': int(data['FORECAST_PAX_BMS'][j]),
            }
        dictData.append(D)
    
    ## Create dataframe from dictionary
    df = pd.DataFrame(dictData)

    return df, list(dictData[6:]), x, y, list_ovtime, time_, mean, err, mean_plus, mean_min


## Function to Generate Picture
def generate_graph(x, y, mean, mean_min, mean_plus, terminal):

    # Create an area chart for the revenue apsd figures
    fig = go.Figure()

    def line_on_chart(x, mean, color):
        return fig.add_shape(
        go.layout.Shape(
            type="line",
            x0=min(x),
            x1=max(x),
            y0=np.round(mean,2),
            y1=np.round(mean,2),
            line=dict(
                color=f"{color}",
                width=2,
                dash="dashdot",
            )
        )
    )

    def line_legend(mean, text, color):
        return fig.add_trace(
        go.Scatter(
            x=[None],  # This trace will not show any data points
            y=[None],
            mode='lines',
            name=f'{text} = {np.round(mean,2)}',  # The legend label
            line=dict(color=f'{color}', dash='dashdot'),
            showlegend=True,
            legendgroup="legendgroup1",  # Optional: use this if you have multiple shapes/lines you want to group in the legend
            visible='legendonly'
        )
    )
    fig.add_trace(
        go.Scatter(
            x=x,
            y=y,
            mode='lines+markers',
            line=dict(color='rgb(255, 45, 165)', width=2.5),
            marker=dict(color='rgb(255, 45, 165)', size=7),
            name='Perkiraan Jumlah Penumpang',
            hovertemplate=f"Terminal {terminal}<br>""Jumlah Penumpang: %{y}",
        )
    )

    # Format the layout
    fig.update_layout(
        title=f"Prakiraan Jumlah Penumpang Bus<br>Terminal {terminal} CGK",
        xaxis_title='Waktu',
        yaxis_title='Jumlah Penumpang',
        title_x=0.5,
        xaxis=dict(
            showline=True,
            showgrid=True,
            showticklabels=True,
            linecolor='gray',
            linewidth=2,
            ticks='outside',
            tickfont=dict(
                family='Arial',
                size=12,
                color='gray',
            ),
        ),
        yaxis=dict(
            showgrid=True,
            gridcolor='lightgray',
            zeroline=False,
            showline=False,
            showticklabels=True,
            tickfont=dict(
                family='Arial',
                size=12,
                color='gray',
            ),
        ),
        template="plotly_white",
        paper_bgcolor='white',
        plot_bgcolor='white',
        margin=dict(r=10, l=20, b=0, t=80, pad=5),
    )

    line_on_chart(x, mean_plus, 'red')
    line_legend(mean_plus, "batas atas", 'red')

    line_on_chart(x, mean, 'orange')
    line_legend(mean, "rata-rata", 'orange')

    line_on_chart(x, mean_min, 'green')
    line_legend(mean_min, "batas bawah", 'green')


    fig.update_layout(
        width=1400,   # Width in pixels
        height=600,  # Height in pixels
    )

    buffer = io.BytesIO()
    fig.write_image(buffer, format='png')
    buffer.seek(0)
    image_base64 = base64.b64encode(buffer.getvalue()).decode()

    return image_base64

# Function to generate text from list of time
def generate_text(list_time):
    list_temp = []
    for i in list_time:
        list_temp.append(f"- {i}\n")
    text = ''''''.join(list_temp)
    return text


def get_info(df, terminal):
    err = math.sqrt(np.var(df['PRAKIRAAN PAX BMS']))

    rslt = df[df['PRAKIRAAN PAX BMS'] > (df['PRAKIRAAN PAX BMS'].mean()+err)]
    for i in rslt['TIME'].values:
        print(f'- {i}')
    print(f"Di Terminal {terminal} pada rentang waktu tersebut  memerlukan perhatian khusus oleh tim yang bertugas.")


def get_pax_bms(df, date_time, terminal):
    num_pax = []
    for i in range(len(date_time[:-1])):
        time2 = datetime.datetime.strptime(str(date_time[i+1]), '%Y-%m-%d %H:%M:%S') - datetime.timedelta(minutes=1)
        temp = df[df['created_on'] > date_time[i]]
        temp = temp[temp['created_on'] < time2]
        temp_ = temp[temp['shelter_name'] == f'T{terminal}']
        num_pax.append(len(temp_))
    return(num_pax)


def Average(data):
    return sum(data) / len(data)

def convert_bit_lenght(data):        
    a = []
    for element in data:
        native_int = int(element)
        a.append(native_int.bit_length())
    return a

def normalize_series(data):
    mean = np.mean(data, axis=0)
    std = np.std(data, axis=0)
    scaled_data = (data - mean) / std
    return scaled_data

def inverse_normalize_series(scaled, original):
    # Mean and standard deviation of the original data
    mean = np.mean(original, axis=0)
    std = np.std(original, axis=0)

    # Inverse Z-score scaling
    original_data = scaled * std + mean
    original_data = np.round(original_data,0)
    return original_data

def model_forecast(model, series, window_size, batch_size):
    ds = tf.data.Dataset.from_tensor_slices(series)
    ds = ds.window(window_size, shift=1, drop_remainder=True)
    ds = ds.flat_map(lambda w: w.batch(window_size))
    ds = ds.batch(batch_size, drop_remainder=True).prefetch(1)
    forecast = model.predict(ds)
    return forecast
