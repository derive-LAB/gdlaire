################################################################################
# Module: Data gathering and treatment
# updated: 12/10/2020
################################################################################

from pathlib import Path
import os
import osmnx as ox
import pandas as pd
import numpy as np
import geopandas as gpd
import xlrd
import urllib.request
import math
from datosgobmx import client
from . import utils

from datetime import datetime, timedelta


def sinaica_stations_csv():
    """Function that downloads csv with information for all Mexican air quality stations using SINAICA api,
        and filters for Guadalajara

    Returns:
        csv -- csv with information for all air quality stations for Guadalajara from the SINAICA database

    """

    # calls datosgobmx function and gathers data
    parametros_request = client.makeCall(
        'sinaica-estaciones', {'pageSize': 200})

    stations = []  # list which saves station information

    # gathers data from all stations and interates over them
    for v in parametros_request['results']:
        aux = pd.DataFrame.from_dict(v, orient='index').T
        stations.append(aux)

    stations = pd.concat(stations, ignore_index=True)

    # Removes stations that are out of Mexico
    #mask = (stations.lat.between(14, 34.5)) & (stations.long.between(-120, -70))
    stations = stations[stations['redesid'] == 63]

    utils.log('CSV with stations coordinates downloaded')

    return stations


def daterange(start_date, end_date, interval='hour', lapse=1):
    """Function that creates a list with dates from start to end according to interval.

    Args:
        start_date (datetime): start datetime value in format yyyy-mm-dd hh:mm.
        end_date (datetime): end datetime value in format yyyy-mm-dd hh:mm.
        interval (str, optional): interval that will be added from start to end date, it can be day or hour. Defaults to 'hour'.
        lapse (int, optional): time lapse increment. Defaults to 1.

    Returns:
        list: list of dates from start_date to end_date according to interval and lapse.
    """

    if interval == 'hour':
        delta = timedelta(hours=lapse)
    elif interval == 'day':
        delta = timedelta(days=lapse)

    date_list = []
    while start_date <= end_date:
        date_list.append(start_date)
        start_date += delta

    return date_list


def simaj_download(year_start=2014, year_end=2019):
    """Function that downloads data from the SIMAJ database

    Args:
        year_start (int, optional): starting year to download. Defaults to 2014.
        year_end (int, optional): end year to download. Defaults to 2019.
    """

    for year in range(year_end-year_start+1):

        save_path = os.path.join(
            '../data/raw/', 'datos_'+str(year_start+year)+'.xlsx')

        urllib.request.urlretrieve(
            'http://siga.jalisco.gob.mx/aire/reportes/datos_'+str(year_start+year)+'.xlsx', save_path)


def database_clean(interval='hour'):
    """Function that creates a new and clean database in .csv format from SIMAJ air quality database for the years 2014 to 2019.

    Args:
        interval (str, optional): it sets the interval for the new database, it can take 'hour' or 'day'. Defaults to 'hour'.
    """

    dir_gdl = '../data/raw/'

    # dictionary for stations codes and names
    est_dict = {'ÁGUILAS': 'AGU', 'AGUILAS': 'AGU', 'LAS ÁGUILAS': 'AGU', 'ATEMAJAC': 'ATM', 'CENTRO': 'CEN',
                'LAS PINTAS': 'PIN', 'LOMA DORADA': 'LDO', 'MIRAVALLE': 'MIR', 'OBLATOS': 'OBL',
                'SANTA FE': 'SFE', 'SANTA FÉ': 'SFE', 'TLAQUEPAQUE': 'TLA', 'VALLARTA': 'VAL'}

    # check for file or directory in dir_gdl
    for file in os.listdir(dir_gdl):

        if file.endswith('.xlsx'):
            # SIMAJ data is in xls and in different sheets
            xls = xlrd.open_workbook(r''+dir_gdl+file, on_demand=True)
            sheets = xls.sheet_names()  # creates list form sheet names

        else:
            continue

        year = file[6:10]  # gathers the year from the file name

        start_date = datetime(int(year), 1, 1, 00, 00)  # start date for array
        end_date = datetime(int(year), 12, 31, 23, 00)  # end date for array

        # creates array for every hour of a given year
        date_array = np.array(
            daterange(start_date, end_date, interval=interval))

        # creates new df in which air quality data for all stations will be saved
        df = pd.DataFrame(index=np.array(range(0, len(date_array))), columns=[
                          'FECHA', 'HORA', 'O3', 'PM10', 'CO', 'NO2', 'SO2'])

        # datetime id counter
        dt_id = 0

        # saves date and hour data to df
        for t in date_array:
            df['FECHA'].iloc[dt_id] = t.date()
            df['HORA'].iloc[dt_id] = '{:02d}:{:02d}'.format(t.hour, t.minute)
            dt_id += 1

        # sets index before stack
        df = df.set_index(['FECHA', 'HORA'])

        # stacks DataFrame so for every date there are 5 rows with criterion pollutants
        df = df.stack(dropna=False)
        df = df.reset_index().rename(columns={'level_2': 'PARAM'})

        # sets index depending on interval type
        if interval == 'hour':
            df = df.set_index(['FECHA', 'HORA', 'PARAM'])
        else:
            df = df.set_index(['FECHA', 'PARAM']).drop(columns='HORA')

        for s in sheets:

            # reads excel with data and sets empty cells as nan
            gdl_data = pd.read_excel(
                dir_gdl+file, sheet_name=s).replace(r'^\s*$', np.nan, regex=True)

            gdl_data.rename(
                columns={gdl_data.columns[0]: 'FECHA', gdl_data.columns[1]: 'HORA'}, inplace=True)

            # fixes column names
            if int(year) == 2014 and s == 'Las Pintas':
                gdl_data.rename(
                    columns={gdl_data.columns[6]: 'SO2'}, inplace=True)

            if int(year) == 2018 and s != 'Vallarta':
                gdl_data.rename(
                    columns={gdl_data.columns[2]: 'O3'}, inplace=True)

            # fixes date
            if int(year) == 2018 and s == 'Centro':
                gdl_data['FECHA'].iloc[4112] = datetime.strptime(
                    '2018-06-21', '%Y-%m-%d')

            gdl_data.columns = gdl_data.columns.str.replace(
                ' ', '')  # removes spaces from columns

            # removes : from columns
            gdl_data.columns = [col.replace(':', '')
                                for col in gdl_data.columns]

            gdl_data = gdl_data[['FECHA', 'HORA', 'O3',
                                 'NO2', 'SO2', 'PM10', 'CO']]  # filters data

            # sets FECHA column as date
            gdl_data['FECHA'] = gdl_data['FECHA'].dt.date

            # iterates over hour data and gives it the appropiate format
            for i in range(len(gdl_data)):

                try:
                    # tries to set hour in hh:mm format according to HORA column
                    gdl_data['HORA'].iloc[i] = '{:02d}:{:02d}'.format(
                        gdl_data['HORA'].iloc[i].hour, gdl_data['HORA'].iloc[i].minute)

                except:

                    # nested tries
                    try:
                        # if HORA is float or int it gives it datetime format
                        time_type = gdl_data['HORA'].iloc[i]
                        seconds = (time_type - 25569) * 86400.0
                        time_datetime = datetime.utcfromtimestamp(seconds)

                        gdl_data['HORA'].iloc[i] = '{:02d}:{:02d}'.format(
                            time_datetime.hour, time_datetime.minute)

                    except:

                        # if HORA is nan it takes previous date and hour and adds +1h and stores it in date and time
                        prev_date = gdl_data['FECHA'].iloc[i-1]
                        prev_hour = gdl_data['HORA'].iloc[i-1]

                        prev_datetime = str(prev_date)+' '+str(prev_hour)

                        date_datetime = datetime.strptime(
                            prev_datetime, '%Y-%m-%d %H:%M')

                        new_datetime = date_datetime + timedelta(hours=1)

                        gdl_data['FECHA'].iloc[i] = new_datetime.date()
                        gdl_data['HORA'].iloc[i] = '{:02d}:{:02d}'.format(
                            new_datetime.hour, new_datetime.minute)

            # stacks gdl DataFrame so for every date there are 5 rows with criterion pollutants
            gdl_stack = pd.DataFrame(gdl_data.set_index(
                ['FECHA', 'HORA']).stack([0], dropna=False))

            # changes name from stacked column with concentration information
            gdl_stack = gdl_stack.reset_index().rename(columns={'level_2': 'PARAM',
                                                                0: est_dict[s.strip(' ').upper()]})

            gdl_stack['FECHA'] = pd.to_datetime(gdl_stack['FECHA'])

            # because the data base contains dates out from the analyzed year the DataFrame is filtered
            gdl_stack = gdl_stack[gdl_stack['FECHA'].dt.year == int(
                file[6:10])]

            # removes sapces from sheet names and sets columns as numbers avoiding spaces
            gdl_stack[est_dict[s.strip(' ').upper()]] = pd.to_numeric(
                gdl_stack[est_dict[s.strip(' ').upper()]], errors='coerce')

            if interval == 'day':
                gdl_stack = gdl_stack.drop(columns=['HORA'])
                gdl_stack = gdl_stack.groupby(['FECHA', 'PARAM']).mean()
            else:
                # it groups data to avoid doble dates in air quality database
                gdl_stack = gdl_stack.groupby(
                    ['FECHA', 'HORA', 'PARAM']).mean()

            # adds data from gdl_stack for a specified year to all_data which
            # will contain information for every year
            df = pd.merge(df, gdl_stack, how='left',
                          left_index=True, right_index=True)

        # drops coloumn 0 which is created when stacking df
        df = df.drop(columns=0)
        # saves data for all years, stations and parameters
        df.to_csv('../gdl-aire/gdlaire/data/processed/' +
                  file[6:10]+'_'+interval+'.csv')


def restructure_database(interval='hour'):
    """Function that takes cleaned databases for air quality data and restructures it into a single DataFrame.

    Args:
        interval (str, optional): it sets the interval for the new database, it can take 'hour' or 'day'. Defaults to 'hour'.

    Returns:
        pandas.DataFrame: pandas DataFrame with columns: FECHA, HORA (depending on interval), PARAM, EST_SIMAJ, CONC, LONG, LAT.
    """
    dir_gdl = '../data/processed/'

    simaj_reestructurado_all = pd.DataFrame()

    # check for file or directory in dir_gdl
    for file in os.listdir(dir_gdl):

        if file.endswith('.csv'):

            if interval in file:

                # read csv of air quality data according to interval
                simaj_data = pd.read_csv(dir_gdl+file)

                simaj_reestructurado = simaj_data.copy()

                # stack stations according to interval
                if interval == 'hour':

                    simaj_reestructurado = pd.DataFrame(simaj_reestructurado.set_index(
                        ['FECHA', 'HORA', 'PARAM']).stack(dropna=False))

                    simaj_reestructurado.reset_index(inplace=True)

                    simaj_reestructurado.rename(
                        columns={'level_3': 'EST_SIMAJ', 0: 'CONC'}, inplace=True)

                else:

                    simaj_reestructurado = pd.DataFrame(
                        simaj_reestructurado.set_index(['FECHA', 'PARAM']).stack(dropna=False))

                    simaj_reestructurado.reset_index(inplace=True)

                    simaj_reestructurado.rename(
                        columns={'level_2': 'EST_SIMAJ', 0: 'CONC'}, inplace=True)

                simaj_reestructurado_all = simaj_reestructurado_all.append(
                    simaj_reestructurado)

            # read df with stations coordinates
            stations_simaj = pd.read_csv('../data/raw/estaciones.csv')

        else:
            continue

    i = 0

    for est in stations_simaj['codigo']:

        # adds coordinates to df
        simaj_reestructurado_all.loc[simaj_reestructurado_all.EST_SIMAJ == est,
                                     'LONG'] = stations_simaj[stations_simaj['codigo'] == est]['long'][i]

        simaj_reestructurado_all.loc[simaj_reestructurado_all.EST_SIMAJ == est,
                                     'LAT'] = stations_simaj[stations_simaj['codigo'] == est]['lat'][i]

        i = i + 1

    return (simaj_reestructurado_all)


def week_average (df, station, interval = 7, year_start=2014, year_end=2019):

    station_column = 'EST_'+station

    df_week = pd.DataFrame(columns=['S_ID','S_YEAR','PARAM',station_column,'CONC','DESV_EST','LONG','LAT'])
    
    year = [y for y in range (year_start, year_end+1)]

    i=0

    for y in year:
        
        for s in range(1,53):
            
            for p in df.PARAM.unique():
                
                for est in df[station_column].unique():
                
                    df_week.loc[i]=['S'+str(s),'S'+str(s)+'-'+str(y), p,
                                    est, np.nan, np.nan, 
                                    df.loc[df[station_column]==est]['LONG'].iloc[0],
                                    df.loc[df[station_column]==est]['LAT'].iloc[0],
                                    ]

                    i+=1
                    

    interval = 7

    for p in df.PARAM.unique():
            
        for est in df[station_column].unique():
                        
            df_analysis = df.loc[(df.PARAM==p)&(df[station_column]==est)]

            divide = int(round((len(df_analysis)/interval),0))

            s = 1

            for i in range(0, divide):

                mean_conc = df_analysis.iloc[i*interval:i*interval+interval]['CONC'].mean()

                std_conc = df_analysis.iloc[i*interval:i*interval+interval]['CONC'].std()

                day_year = i*interval+int((((i*interval+interval)-(i*interval))/2)-0.5)
                
                year_df = df_analysis['FECHA'].iloc[day_year].year
                
                df_week.loc[(df_week.S_ID=='S'+str(s)) & 
                        (df_week.S_YEAR=='S'+str(s)+'-'+str(year_df)) & 
                        (df_week.PARAM==p) &
                            (df_week[station_column]==est),
                            'CONC'] = mean_conc

                df_week.loc[(df_week.S_ID=='S'+str(s)) & 
                        (df_week.S_YEAR=='S'+str(s)+'-'+str(year_df)) & 
                        (df_week.PARAM==p) &
                            (df_week[station_column]==est),
                            'DESV_EST'] = std_conc

                s += 1

                if s > 52:

                    s = 0

    return (df_week)


def download_graph(polygon, network_type='walk'):
    """Download a graph from a bounding box, and saves it to disk

    Arguments:
            polygon {polygon} -- polygon to use as boundary to download the network

    Keyword Arguments:
            network_type {str} -- String with the type of network to download (drive, walk, bike, all_private, all) for more details see OSMnx documentation

    Returns:
            nx.MultiDiGraph
    """
    utils.log("Downloading graph")
    G = ox.graph_from_polygon(polygon, network_type=network_type,
                              simplify=True, retain_all=False, truncate_by_edge=False)
    utils.log('Graph downloaded')
    return G


def save_graph(G, city):
    """Load the nodes/edges from a graph G to database

    Args:
        G (osmnx.Graph): Grpah created/retrived from OSMnx
        city (str): name of the city, this is used to create the tables {city}_nodes and {city}_edges
    """
    utils.log('Getting nodes and edges')
    nodes, edges = ox.graph_to_gdfs(G)
    utils.log('Nodes and eges loaded')
    engine = utils.db_engine()
    utils.log('Uploading nodes')
    nodes.to_postgis(name=f'{city.lower()}_nodes', con=engine,
                     if_exists='fail',  schema="networks", index=False)
    utils.log('Nodes uploaded')
    utils.log('Uploading edges')
    edges.to_postgis(name=f'{city.lower()}_edges', con=engine,
                     if_exists='fail', schema="networks", index=False)
    utils.log('Edges uploaded')


def graph_from_db(city):
    """Download the graph from a city from the database

    Args:
        city (str): name of the city

    Returns:
        osmnx.Graph: multiDirected graph to work with osmnx
    """
    engine = utils.db_engine()
    nodes = gpd.read_postgis(
        f"SELECT * FROM networks.{city.lower()}_nodes", engine, geom_col='geometry', index_col='osmid')
    utils.log('Nodes loaded')
    edges = gpd.read_postgis(
        f"SELECT * FROM networks.{city.lower()}_edges", engine, geom_col='geometry', index_col='osmid')
    utils.log('Edges loaded')
    G = ox.graph_from_gdfs(nodes, edges)
    utils.log("Graph created")
    return G


def create_schema(schema):
    engine = utils.db_engine()

    # Create schema; if it already exists, skip this
    try:
        engine.execute(f'CREATE SCHEMA IF NOT EXISTS {schema.lower()}')
    except Exception as e:
        utils.log(e)
        pass


def df_to_db(df, name, schema, if_exists='fail'):
    """Upload a Pandas.DataFrame to the database

    Args:
        df (pandas.DataFrame): DataFrame to be uploadead
        name (str): Name of the table to be created
        schema (str): Name of the folder in which to save the geoDataFrame
        if_exists (str): Behaivor if the table already exists in the database ('fail', 'replace', 'append') 'fail' by default.
    """
    create_schema(schema)
    utils.log('Getting DB connection')
    engine = utils.db_engine()
    utils.log(f'Uploading table {name} to database')
    df.to_sql(name=name.lower(), con=engine,
              if_exists=if_exists, index=False, schema=schema.lower(), method='multi', chunksize=50000)
    utils.log(f'Table {name} in DB')


def df_from_db(name, schema):
    """Load a table from the database into a DataFrame

    Args:
        name (str): Name of the table to be loaded
        schema (str): Name of the folder from where to load the geoDataFrame

    Returns:
        pandas.DataFrame: GeoDataFrame with the table from the database.
    """
    engine = utils.db_engine()
    utils.log(f'Getting {name} from DB')
    df = pd.read_sql(
        f"SELECT * FROM {schema.lower()}.{name.lower()}", engine)
    utils.log(f'{name} retrived')
    return df


def df_from_query(query):
    """Load a table from the database into a DataFrame

    Args:
        query (str): SQL query to get the data

    Returns:
        pandas.DataFrame: GeoDataFrame with the table from the database.
    """
    engine = utils.db_engine()
    utils.log('Getting data from DB')
    df = pd.read_sql(query, engine)
    utils.log('Data retrived')
    return df


def gdf_to_db(gdf, name, schema, if_exists='fail'):
    """Upload a geoPandas.GeoDataFrame to the database

    Args:

        gdf (geopandas.GeoDataFrame): GeoDataFrame to be uploadead

        name (str): Name of the table to be created

        schema (str): Name of the folder in which to save the geoDataFrame

        if_exists (str): Behaivor if the table already exists in the database ('fail', 'replace', 'append') 'fail' by default. 

    """

    create_schema(schema)

    utils.log('Getting DB connection')

    engine = utils.db_engine()

    utils.log(f'Uploading table {name} to database')

    gdf.to_postgis(name=name.lower(), con=engine,
                   if_exists=if_exists, index=False, schema=schema.lower())

    utils.log(f'Table {name} in DB')


def gdf_from_db(name, schema):
    """Load a table from the database into a GeoDataFrame

    Args:
        name (str): Name of the table to be loaded
        schema (str): Name of the folder from where to load the geoDataFrame

    Returns:
        geopandas.GeoDataFrame: GeoDataFrame with the table from the database.
    """
    engine = utils.db_engine()
    utils.log(f'Getting {name} from DB')
    gdf = gpd.read_postgis(
        f"SELECT * FROM {schema.lower()}.{name.lower()}", engine, geom_col='geometry')
    utils.log(f'{name} retrived')
    return gdf
