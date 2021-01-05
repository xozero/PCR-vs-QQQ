import time
import datetime
import threading
from collections import defaultdict

import pandas as pd
import requests
from bs4 import BeautifulSoup
from flask import Flask
from flask import render_template


def update_from_remote():
    # Update PCR
    equity_new_df = pd.read_csv('equity_new.csv')
    start_date = datetime.datetime.strptime(
        equity_new_df.tail(1)['date'].tolist()[0],
        "%Y-%m-%d"
    ) + datetime.timedelta(days=1)
    # PCR not available for current day yet, so remove one day.
    end_date = datetime.date.today() - datetime.timedelta(days=1)
    daterange = pd.date_range(start_date, end_date, freq='B')

    print('Range', daterange)

    url = 'https://markets.cboe.com/us/options/market_statistics/daily/?mkt=cone&dt=%s'  # noqa

    kv = defaultdict(list)
    for single_date in daterange:
        datestr = single_date.strftime("%Y-%m-%d")
        print('Getting', datestr)
        r = requests.get(url % datestr)
        soup = BeautifulSoup(r.text, "html.parser")

        for item in soup.select("table.bats-table"):
            raw = [item_.string for item_ in item.select(".bats-td--left")]
            tuples = list(zip(raw[::2], raw[1::2]))
            for k, v in tuples:
                kv[str(k)].append(float(v))
        kv['date'].append(datestr)

    df = pd.DataFrame.from_dict(kv)
    equity_new_df = equity_new_df.append(df, ignore_index=True)
    equity_new_df.to_csv('equity_new.csv')

    # Update QQQ
    url = 'https://query1.finance.yahoo.com/v7/finance/download/QQQ?period1=1162166400&period2=%s&interval=1d&events=history&includeAdjustedClose=true'  # noqa
    datestr = str(int(datetime.datetime.today().timestamp()))
    r = requests.get(url % datestr)
    with open('QQQ.csv', 'w+') as f:
        f.write(r.text)


def update_worker():
    print('Running update worker in background.')
    global pcr_data, qqq_data
    while True:
        update_from_remote()
        pcr_data, qqq_data = load_all()
        time.sleep(60 * 60 * 6)  # 6 hours


def load_all():
    # Load Equity P/C Ratio
    df = pd.read_csv('equitypc.csv', sep=',')
    equity_new_df = pd.read_csv('equity_new.csv')

    df['DATE'] = pd.to_datetime(df['DATE'])
    dates = df['DATE'].tolist()
    pcratios = df['P/C Ratio'].tolist()

    equity_new_df['date'] = pd.to_datetime(equity_new_df['date'])
    dates.extend(equity_new_df['date'].tolist())
    pcratios.extend(equity_new_df['EQUITY PUT/CALL RATIO'].tolist())

    # Load QQQ
    df = pd.read_csv('QQQ.csv', sep=',')
    df['Date'] = pd.to_datetime(df['Date'])
    qqq_dates = df['Date'].tolist()
    qqq_prices = df['Adj Close'].tolist()

    pcr_data = []
    qqq_data = []
    for (date, pcratio) in zip(dates, pcratios):
        pcr_data.append([int(date.timestamp()) * 1000, pcratio])
    for (date, price) in zip(qqq_dates, qqq_prices):
        qqq_data.append([int(date.timestamp()) * 1000, price])

    # return dates, pcratios, qqq_dates, qqq_prices
    return pcr_data, qqq_data


app = Flask(__name__, static_url_path='/static')
# Load data into memory.
pcr_data, qqq_data = load_all()


@app.route('/', methods=['GET'])
def index():
    return render_template(
        "index.j2",
        pcr_data=pcr_data,
        qqq_data=qqq_data,
    )


def start_thread():
    t = threading.Thread(target=update_worker)
    t.daemon = True
    t.start()


if __name__ == '__main__':
    start_thread()
    app.run(host='0.0.0.0')
