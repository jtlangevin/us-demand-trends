#!/usr/bin/env python3
"""
master.py

A live-data pipeline for extracting, cleaning, and
visualizing U.S. buildings sector data from federal APIs.
No dummy data is used. Requires valid API keys for BLS, EIA, BEA, ITA,
and the US Census Bureau.
Saves all outputs as static .html files.
"""

import os
import zipfile
import io
import json
from urllib.request import urlopen, Request
import pandas as pd
import requests
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import plotly.express as px
import re
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
import numpy as np
import geopandas as gpd
import warnings
import traceback
from shapely.errors import ShapelyDeprecationWarning
from dotenv import load_dotenv
import time
from datetime import datetime

# Suppress geometry warnings for cleaner output
warnings.filterwarnings("ignore", category=ShapelyDeprecationWarning)
warnings.filterwarnings("ignore", message=".*Geometry is in a geographic CRS.*")
# Silence openpyxl's complaints about Census Excel print formatting
warnings.filterwarnings('ignore', category=UserWarning, module='openpyxl')


# ==========================================
# 1. LIVE DATA EXTRACTION FUNCTIONS
# ==========================================

def fetch_eia_v2_data(route, params, api_key):
    """Fetches data from the EIA API v2."""
    if not api_key:
        raise ValueError("EIA API key is missing.")

    url = f"https://api.eia.gov/v2/{route}"
    params['api_key'] = api_key

    resp = requests.get(url, params=params)
    resp.raise_for_status()
    data = resp.json()

    if 'response' in data and 'data' in data['response']:
        return pd.DataFrame(data['response']['data'])
    raise RuntimeError(f"EIA API Error: {data}")


# ==========================================
# 2. DATA PROCESSING & VISUALIZATION
# ==========================================

def plot_energy_burden(output_dir):
    """Superimposes electric vs total energy burden dual-map HTML."""
    print("Plotting: Energy burden by state (EIA RECS)...")
    recs_df = None
    target_year = pd.Timestamp.now().year
    found_year = 2020  # Fallback minimum

    while target_year >= 2020:
        for v in range(5, 0, -1):
            url = (
                "https://www.eia.gov/consumption/residential/data/"
                f"{target_year}/csv/recs{target_year}_public_v{v}.csv"
            )
            try:
                r = requests.head(url, timeout=5)
                if r.status_code == 200:
                    print(f" -> Success! Found RECS {target_year} (v{v})")
                    recs_df = pd.read_csv(url, usecols=[
                        'state_postal', 'TOTALDOL', 'DOLLAREL', 'MONEYPY'
                    ])
                    found_year = target_year
                    break
            except Exception:
                pass

        if recs_df is not None:
            break
        target_year -= 1

    if recs_df is None:
        print("\n[ERROR] Could not find any valid RECS data.")
        return

    df = recs_df.copy()
    income_map = {
        1: 2500, 2: 6250, 3: 8750, 4: 11250, 5: 13750,
        6: 17500, 7: 22500, 8: 27500, 9: 32500, 10: 37500,
        11: 45000, 12: 55000, 13: 67500, 14: 87500,
        15: 125000, 16: 175000
    }

    df = df[df['MONEYPY'].isin(income_map.keys())].copy()
    df['Income_Est'] = df['MONEYPY'].map(income_map)
    df['Total_Burden_Pct'] = (df['TOTALDOL'] / df['Income_Est']) * 100
    df['Electric_Burden_Pct'] = (df['DOLLAREL'] / df['Income_Est']) * 100

    cols = ['Total_Burden_Pct', 'Electric_Burden_Pct']
    state_burden = df.groupby('state_postal')[cols].median().reset_index()
    state_burden = state_burden.sort_values('Total_Burden_Pct', ascending=True)

    max_burden = state_burden['Total_Burden_Pct'].max()

    fig = make_subplots(
        rows=2, cols=2,
        row_heights=[0.6, 0.4],
        vertical_spacing=0.15,
        horizontal_spacing=0.05,
        specs=[
            [{'type': 'choropleth'}, {'type': 'choropleth'}],
            [{'type': 'bar', 'colspan': 2}, None]
        ],
        subplot_titles=(
            f"Total Energy Burden, {found_year}<br><sup>Source: RECS</sup>",
            f"Electric Energy Burden, {found_year}<br><sup>Source: RECS</sup>",
            f"Total and Electric Energy Burden by State, {found_year}"
            "<br><sup>Source: RECS</sup>"
        )
    )

    annotations = list(fig.layout.annotations)
    annotations[0].yshift = -20
    annotations[1].yshift = -20
    annotations[2].x = 0.55
    fig.layout.annotations = annotations

    fig.add_trace(
        go.Choropleth(
            locations=state_burden['state_postal'],
            z=state_burden['Total_Burden_Pct'],
            locationmode="USA-states", colorscale="magma",
            zmin=0, zmax=max_burden,
            colorbar=dict(title="Median %", x=0.46, len=0.45, y=0.70),
            hovertemplate=(
                "<b>%{location}</b><br>"
                "Total: %{z:.2f}%<extra></extra>"
            )
        ), row=1, col=1
    )

    fig.add_trace(
        go.Choropleth(
            locations=state_burden['state_postal'],
            z=state_burden['Electric_Burden_Pct'],
            locationmode="USA-states", colorscale="magma",
            zmin=0, zmax=max_burden,
            colorbar=dict(title="Median %", x=1.02, len=0.45, y=0.70),
            hovertemplate=(
                "<b>%{location}</b><br>"
                "Elec: %{z:.2f}%<extra></extra>"
            )
        ), row=1, col=2
    )

    fig.add_trace(go.Bar(
        y=state_burden['state_postal'], x=state_burden['Total_Burden_Pct'],
        name='Total Energy Burden', orientation='h',
        marker=dict(color='lightgray'),
        hovertemplate="Total Burden: %{x:.2f}%<extra></extra>"
    ), row=2, col=1)

    fig.add_trace(go.Bar(
        y=state_burden['state_postal'], x=state_burden['Electric_Burden_Pct'],
        name='Electric Burden Only', orientation='h',
        marker=dict(color='#636EFA'),
        hovertemplate="Electric Burden: %{x:.2f}%<extra></extra>"
    ), row=2, col=1)

    fig.update_layout(
        dragmode="pan",
        height=1200, barmode='overlay',
        geo=dict(scope='usa', projection_type='albers usa'),
        geo2=dict(scope='usa', projection_type='albers usa'),
        margin={"r": 0, "t": 40, "l": 0, "b": 60},
        legend=dict(
            orientation="h", yanchor="top", y=-0.04, xanchor="center", x=0.5
        )
    )

    fig.update_xaxes(
        title_text="Median Energy Burden (% of Income)",
        domain=[0.20, 0.90], row=2, col=1
    )
    fig.update_yaxes(title_text="State", row=2, col=1)

    html_maps_path = f"{output_dir}/energy_burden_maps_bar.html"
    fig.write_html(
        html_maps_path, default_width='95%', default_height='100%',
        config={'scrollZoom': True}
    )
    print(f" -> Success! Energy burden HTML saved to {html_maps_path}")


def plot_fuel_price_ratio(eia_key, output_dir):
    """Plotly version ranking residential and commercial fuel price ratios."""
    print("Plotting: Fuel price ratios by state and sector (EIA API)...")

    def get_elec_data(sector_id, col_name):
        params = {
            "frequency": "annual", "data[0]": "price",
            "facets[sectorid][]": sector_id, "start": "2018", "length": 5000
        }
        df = fetch_eia_v2_data(
            "electricity/retail-sales/data/", params, eia_key
        )
        df = df[df['stateid'] != 'US'].copy()
        df['price'] = pd.to_numeric(df['price'], errors='coerce')
        df = df.dropna(subset=['price'])
        df['Year'] = pd.to_numeric(df['period'], errors='coerce').astype(int)
        df = df.rename(columns={'stateid': 'State', 'price': col_name})
        return df[['State', 'Year', col_name]].drop_duplicates(
            subset=['State', 'Year']
        )

    def get_ng_data(process_id, col_name):
        params = {
            "frequency": "annual", "data[0]": "value",
            "facets[process][]": process_id, "start": "2018", "length": 5000
        }
        df = fetch_eia_v2_data("natural-gas/pri/sum/data/", params, eia_key)
        df['value'] = pd.to_numeric(df['value'], errors='coerce')
        df = df.dropna(subset=['value'])
        df['Year'] = pd.to_numeric(df['period'], errors='coerce').astype(int)
        df = df[df['duoarea'].str.match(r'^S[A-Z]{2}$', na=False)].copy()
        df['State'] = df['duoarea'].str[1:]
        df = df.rename(columns={'value': col_name})
        return df[['State', 'Year', col_name]].drop_duplicates(
            subset=['State', 'Year']
        )

    df_elec_res = get_elec_data("RES", "Elec_Cents_kWh_RES")
    df_elec_com = get_elec_data("COM", "Elec_Cents_kWh_COM")
    df_ng_res = get_ng_data("PRS", "NG_Dol_Mcf_RES")
    df_ng_com = get_ng_data("PCS", "NG_Dol_Mcf_COM")

    df_merged = pd.merge(
        df_elec_res, df_elec_com, on=['State', 'Year'], how='inner'
    ).merge(
        df_ng_res, on=['State', 'Year'], how='inner'
    ).merge(
        df_ng_com, on=['State', 'Year'], how='inner'
    )

    state_counts = df_merged.groupby('Year')['State'].nunique()
    if state_counts.empty:
        print("\n[WARNING] Merge failed. Could not find overlapping years.")
        return

    max_states = state_counts.max()
    target_year = max(state_counts[state_counts == max_states].index.tolist())
    df_final = df_merged[df_merged['Year'] == target_year].copy()

    df_final['Elec_Dol_MMBtu_RES'] = (
        df_final['Elec_Cents_kWh_RES'] / 100
    ) / 0.003412

    df_final['NG_Dol_MMBtu_RES'] = df_final['NG_Dol_Mcf_RES'] / 1.032
    df_final['Ratio_RES'] = (
        df_final['Elec_Dol_MMBtu_RES'] / df_final['NG_Dol_MMBtu_RES']
    )

    df_final['Elec_Dol_MMBtu_COM'] = (
        df_final['Elec_Cents_kWh_COM'] / 100
    ) / 0.003412

    df_final['NG_Dol_MMBtu_COM'] = df_final['NG_Dol_Mcf_COM'] / 1.032
    df_final['Ratio_COM'] = (
        df_final['Elec_Dol_MMBtu_COM'] / df_final['NG_Dol_MMBtu_COM']
    )
    df_final = df_final.sort_values('Ratio_RES', ascending=True)

    fig = make_subplots(
        rows=2, cols=2,
        row_heights=[0.6, 0.4],
        vertical_spacing=0.15,
        horizontal_spacing=0.05,
        specs=[
            [{'type': 'choropleth'}, {'type': 'choropleth'}],
            [{'type': 'bar', 'colspan': 2}, None]
        ],
        subplot_titles=(
            f"Residential Customers, {target_year}<br>"
            "<sup>Source: EIA Surveys</sup>",
            f"Commercial Customers, {target_year}<br>"
            "<sup>Source: EIA Surveys</sup>",
            f"Electric vs. Gas Price Ratio by State, {target_year}<br>"
            "<sup>Source: EIA</sup>"
        )
    )

    annotations = list(fig.layout.annotations)
    annotations[0].yshift = -20
    annotations[1].yshift = -20
    annotations[2].x = 0.55
    fig.layout.annotations = annotations

    fig.add_trace(
        go.Choropleth(
            locations=df_final['State'], z=df_final['Ratio_RES'],
            locationmode="USA-states", colorscale="viridis",
            colorbar=dict(title="Elec/Gas<br>Price Ratio", x=0.46,
                          len=0.45, y=0.70),
            hovertemplate=(
                "<b>%{location}</b><br>Res: %{z:.2f}x<extra></extra>"
            )
        ), row=1, col=1
    )

    fig.add_trace(
        go.Choropleth(
            locations=df_final['State'], z=df_final['Ratio_COM'],
            locationmode="USA-states", colorscale="plasma",
            colorbar=dict(title="Elec/Gas<br>Price Ratio", x=1.02,
                          len=0.45, y=0.70),
            hovertemplate=(
                "<b>%{location}</b><br>Com: %{z:.2f}x<extra></extra>"
            )
        ), row=1, col=2
    )

    fig.add_trace(go.Bar(
        y=df_final['State'], x=df_final['Ratio_RES'],
        name='Residential Customers', orientation='h',
        marker=dict(color='#636EFA'),
        hovertemplate="Residential: %{x:.2f}x<extra></extra>"
    ), row=2, col=1)

    fig.add_trace(go.Bar(
        y=df_final['State'], x=df_final['Ratio_COM'],
        name='Commercial Customers', orientation='h',
        marker=dict(color='#EF553B'),
        hovertemplate="Commercial: %{x:.2f}x<extra></extra>"
    ), row=2, col=1)

    fig.update_layout(
        dragmode="pan",
        height=1200, barmode='group',
        geo=dict(scope='usa', projection_type='albers usa'),
        geo2=dict(scope='usa', projection_type='albers usa'),
        margin={"r": 0, "t": 40, "l": 0, "b": 60},
        legend=dict(
            orientation="h", yanchor="top", y=-0.04, xanchor="center", x=0.5
        )
    )

    fig.update_xaxes(
        title_text="Price Ratio", domain=[0.20, 0.90], row=2, col=1
    )
    fig.update_yaxes(title_text="State", row=2, col=1)

    html_maps_path = f"{output_dir}/fuel_price_ratio_maps_bar.html"
    fig.write_html(
        html_maps_path, default_width='95%', default_height='100%',
        config={'scrollZoom': True}
    )
    print(f" -> Success! Fuel price HTML saved to {html_maps_path}")


def fetch_and_clean_census_regions():
    """Helper: Fetches and parses the live Census SOC Excel files."""
    print(" -> Downloading live SOC duration tables from Census...")
    url_a = "https://www.census.gov/construction/nrc/xls/avg_authtostart_cust.xlsx"
    url_c = "https://www.census.gov/construction/nrc/xls/avg_starttocomp_cust.xlsx"
    headers = {'User-Agent': 'Mozilla/5.0'}

    try:
        r_auth = requests.get(url_a, headers=headers, timeout=15)
        r_comp = requests.get(url_c, headers=headers, timeout=15)
        r_auth.raise_for_status()
        r_comp.raise_for_status()
    except Exception as e:
        print(f"❌ Failed to fetch Census SOC files: {e}")
        return None

    regions = {1: "Northeast", 2: "Midwest", 3: "South", 4: "West"}
    master_data = {}
    reporting_year = 0

    def extract_metrics(excel_bytes, sheet_index):
        df = pd.read_excel(
            io.BytesIO(excel_bytes), sheet_name=sheet_index, header=None
        )
        latest_year = 0
        val_sf, val_mf = 0.0, 0.0

        for _, row in df.iterrows():
            col_val = str(row[0]).strip()
            if col_val.isdigit() and len(col_val) == 4:
                year = int(col_val)
                if year > latest_year:
                    latest_year = year
                    val_sf = pd.to_numeric(row[1], errors='coerce')
                    val_mf = pd.to_numeric(row[5], errors='coerce')
        return val_sf, val_mf, latest_year

    for sheet_idx, region_name in regions.items():
        auth_sf, auth_mf, auth_year = extract_metrics(r_auth.content, sheet_idx)
        comp_sf, comp_mf, comp_year = extract_metrics(r_comp.content, sheet_idx)
        reporting_year = max(reporting_year, auth_year, comp_year)

        master_data[region_name] = {
            "SF_Auth": auth_sf if pd.notna(auth_sf) else 0.0,
            "MF_Auth": auth_mf if pd.notna(auth_mf) else 0.0,
            "SF_Build": comp_sf if pd.notna(comp_sf) else 0.0,
            "MF_Build": comp_mf if pd.notna(comp_mf) else 0.0
        }

    return master_data, list(regions.values()), reporting_year


def plot_permits_construction(census_key, output_dir):
    """Permits, cost maps, detailed cost breakdown, and build duration."""
    print("Plotting: Housing permits and costs (Census BPS/SOC)...")

    base_url = 'https://raw.githubusercontent.com/plotly/datasets/master/'
    geojson_url = f'{base_url}geojson-counties-fips.json'

    try:
        with urlopen(geojson_url) as response:
            counties = json.load(response)
    except Exception as e:
        print(f"\n[WARNING] Failed to download county GeoJSON. Error: {e}")
        return

    target_year = pd.Timestamp.now().year
    success_bps = False

    while target_year >= 2020:
        yr_str = str(target_year)[-2:]
        url_a = f"https://www2.census.gov/econ/bps/County/co{yr_str}a.txt"
        url_y = f"https://www2.census.gov/econ/bps/County/co{yr_str}12y.txt"

        for url in [url_a, url_y]:
            try:
                df = pd.read_csv(
                    url, dtype=str, on_bad_lines='skip',
                    storage_options={'timeout': 10}
                )
                if len(df) > 1000:
                    print(f" -> Success! Found BPS data for {target_year}.")
                    success_bps = True
                    break
            except Exception:
                pass

        if success_bps:
            break
        target_year -= 1

    if not success_bps:
        return

    df = df.iloc[:, [0, 1, 4, 6, 7]].copy()
    df.columns = ['SF', 'CF', 'Name', 'Units', 'Value']
    df['SF'] = df['SF'].astype(str).str.strip().str.zfill(2)
    df['CF'] = df['CF'].astype(str).str.strip().str.zfill(3)
    df['FIPS'] = df['SF'] + df['CF']
    df['Units'] = pd.to_numeric(df['Units'], errors='coerce').fillna(0)
    df['Value'] = pd.to_numeric(df['Value'], errors='coerce').fillna(0)
    df = df[pd.to_numeric(df['SF'], errors='coerce') < 60]

    pop_year = target_year
    success_pop = False

    while pop_year >= 2020:
        p_url = f"https://api.census.gov/data/{pop_year}/acs/acs5"
        p_params = {"get": "B01003_001E", "for": "county:*", "key": census_key}
        try:
            resp = requests.get(p_url, params=p_params, timeout=15)
            if resp.status_code == 200:
                p_data = resp.json()
                df_pop = pd.DataFrame(p_data[1:], columns=p_data[0])
                df_pop['FIPS'] = (
                    df_pop['state'].str.zfill(2) + df_pop['county'].str.zfill(3)
                )
                df_pop['Population'] = pd.to_numeric(
                    df_pop['B01003_001E'], errors='coerce'
                )
                df_pop = df_pop[['FIPS', 'Population']].dropna()
                success_pop = True
                break
        except Exception:
            pass
        pop_year -= 1

    df_m = pd.merge(df, df_pop, on='FIPS', how='inner') if success_pop else df
    ct_crosswalk = {
        '09110': '09003', '09120': '09001', '09130': '09007',
        '09140': '09009', '09150': '09015', '09160': '09005',
        '09170': '09009', '09180': '09011', '09190': '09001'
    }
    df_m['FIPS'] = df_m['FIPS'].replace(ct_crosswalk)
    df_m = df_m.groupby('FIPS', as_index=False).agg(
        {'Name': 'first', 'Units': 'sum', 'Value': 'sum', 'Population': 'sum'}
    )

    df_v = df_m[(df_m['Population'] > 0) & (df_m['Units'] > 0)].copy()
    df_v['Permits_1k'] = (df_v['Units'] / df_v['Population']) * 1000
    df_v['Cost'] = df_v['Value'] / df_v['Units']
    max_p = df_v['Permits_1k'].quantile(0.95)
    min_c = df_v['Cost'].min()
    max_c = df_v['Cost'].quantile(0.95)

    # -------------------------------------------------------------
    # LOAD AND PROCESS NAHB DATA (Single-Family Baseline)
    # -------------------------------------------------------------
    try:
        df_full = pd.read_csv('input_data/cost_comps_full.csv')
        df_overhead = pd.read_csv('input_data/cost_comps_overhead.csv')
    except Exception as e:
        print(f"\n[WARNING] Could not load cost_comps files. Error: {e}")
        return

    def get_clean_cost(val):
        if isinstance(val, str):
            return float(val.replace('$', '').replace(',', ''))
        return float(val)

    def get_clean_label(label):
        label = re.sub(r'^[A-Z]+\.\s*', '', label)
        return re.sub(r'^[IVX]+\.\s*', '', label).strip()

    cost_const = get_clean_cost(df_overhead.iloc[1].iloc[5])
    non_const_indices = [0, 2, 3, 4, 5, 6]
    cost_non_const = sum([
        get_clean_cost(df_overhead.iloc[i].iloc[5]) for i in non_const_indices
    ])

    df1 = pd.DataFrame([
        {'Label': 'Total Const. Costs', 'Cost': cost_const, 'Group': 'Const'},
        {'Label': 'Non-Const. Costs', 'Cost': cost_non_const, 'Group': 'Non'}
    ]).sort_values('Cost', ascending=False)

    const_indices = [0, 6, 9, 15, 20, 25, 37, 43]
    const_sub = []
    for i in const_indices:
        const_sub.append({
            'Label': get_clean_label(df_full.iloc[i].iloc[0]),
            'Cost': get_clean_cost(df_full.iloc[i].iloc[5]),
            'Group': 'Const'
        })

    non_const_sub = []
    for i in non_const_indices:
        non_const_sub.append({
            'Label': get_clean_label(df_overhead.iloc[i].iloc[0]),
            'Cost': get_clean_cost(df_overhead.iloc[i].iloc[5]),
            'Group': 'Non'
        })

    df2 = pd.DataFrame(const_sub + non_const_sub)
    df2_sorted = pd.concat([
        df2[df2['Group'] == 'Const'].sort_values('Cost', ascending=False),
        df2[df2['Group'] == 'Non'].sort_values('Cost', ascending=False)
    ])

    total_price = cost_const + cost_non_const

    def add_legend_labels(df_source, total):
        df_source['Percent'] = df_source['Cost'] / total * 100
        df_source['LegendLabel'] = df_source.apply(
            lambda x: (
                f"{x['Label']} (${x['Cost']/1000:.0f}K - {x['Percent']:.0f}%)"
            ), axis=1
        )
        return df_source

    df1 = add_legend_labels(df1, total_price)
    df2_sorted = add_legend_labels(df2_sorted, total_price)

    cmap_red = plt.get_cmap('Reds')
    cmap_blue = plt.get_cmap('Blues')

    df2_sorted['Color'] = [
        mcolors.to_hex(cmap_red(x))
        for x in np.linspace(0.4, 0.9, len(df2[df2['Group'] == 'Const']))
    ] + [
        mcolors.to_hex(cmap_blue(x))
        for x in np.linspace(0.4, 0.9, len(df2[df2['Group'] == 'Non']))
    ]

    # -------------------------------------------------------------
    # LOAD TERNER CENTER DATA (Multi-Family Comparative Baseline)
    # -------------------------------------------------------------
    terner_high = pd.DataFrame([
        {'Label': 'Hard Costs', 'Percent': 65.0, 'Group': 'Hard'},
        {'Label': 'Soft Costs', 'Percent': 22.0, 'Group': 'Soft'},
        {'Label': 'Land Acquisition', 'Percent': 13.0, 'Group': 'Land'}
    ])
    terner_high['LegendLabel'] = terner_high.apply(
        lambda x: f"{x['Label']} ({x['Percent']:.0f}%)", axis=1
    )

    # Read the detailed breakdown dynamically from the inputs folder
    try:
        terner_det = pd.read_csv('input_data/terner_cost_breakdown.csv')
    except Exception as e:
        print(f"\n[WARNING] Could not load terner_cost_breakdown.csv: {e}")
        return

    terner_det['LegendLabel'] = terner_det.apply(
        lambda x: f"{x['Label']} ({x['Percent']:.0f}%)", axis=1
    )

    # Assign colors dynamically matching NAHB structure (Reds/Blues) + Greens
    terner_det['Color'] = (
        [mcolors.to_hex(cmap_red(x)) for x in np.linspace(0.4, 0.9, 6)] +
        [mcolors.to_hex(cmap_blue(x)) for x in np.linspace(0.4, 0.9, 4)] +
        ['#81C784']
    )

    # -------------------------------------------------------------
    # DURATION DATA (CENSUS SOC)
    # -------------------------------------------------------------
    parsed_soc = fetch_and_clean_census_regions()
    if parsed_soc:
        soc_data, regions_list, soc_year = parsed_soc
        x_soc = [
            [reg for reg in regions_list for _ in range(2)],
            ["SF", "MF"] * len(regions_list)
        ]
        y_soc_auth, y_soc_build = [], []
        for reg in regions_list:
            y_soc_auth.extend(
                [soc_data[reg]["SF_Auth"], soc_data[reg]["MF_Auth"]]
            )
            y_soc_build.extend(
                [soc_data[reg]["SF_Build"], soc_data[reg]["MF_Build"]]
            )
    else:
        soc_year = "Data Unavailable"

    # -------------------------------------------------------------
    # BUILD DASHBOARD
    # -------------------------------------------------------------
    fig = make_subplots(
        rows=2, cols=2,
        row_heights=[0.6, 0.4],
        vertical_spacing=0.15,
        horizontal_spacing=0.15,
        specs=[
            [{'type': 'choropleth'}, {'type': 'choropleth'}],
            [{'type': 'bar'}, {'type': 'bar'}]
        ],
        subplot_titles=(
            f"New Housing Permits, {target_year}<br>"
            "<sup>Source: Census BPS</sup>",
            f"New Housing Construction Cost, {target_year}<br>"
            "<sup>Source: Census BPS</sup>",
            f"Average Build Duration by Region, {soc_year}<br>"
            "<sup>Source: Census SOC</sup>",
            "Cost Breakdown: Single-Family<br><sup>Source: NAHB (2024)</sup>"
        )
    )

    annotations = list(fig.layout.annotations)
    annotations[0].yshift = -20
    annotations[1].yshift = -20
    fig.layout.annotations = annotations

    # Maps
    fig.add_trace(
        go.Choropleth(
            geojson=counties, locations=df_v['FIPS'],
            z=df_v['Permits_1k'], colorscale="Inferno",
            zmin=0, zmax=max_p, marker_line_width=0,
            colorbar=dict(title="Permits/1k", x=0.46, len=0.45, y=0.75),
            customdata=df_v[['Name', 'Units', 'Population']],
            hovertemplate=(
                "<b>%{customdata[0]}</b><br>"
                "1k Rate: %{z:.2f}<extra></extra>"
            )
        ), row=1, col=1
    )

    fig.add_trace(
        go.Choropleth(
            geojson=counties, locations=df_v['FIPS'],
            z=df_v['Cost'], colorscale="Inferno",
            zmin=min_c, zmax=max_c, marker_line_width=0,
            colorbar=dict(title="Avg Cost ($)", x=1.02, len=0.45, y=0.75),
            customdata=df_v[['Name', 'Units']],
            hovertemplate=(
                "<b>%{customdata[0]}</b><br>"
                "Cost: $%{z:,.0f}<extra></extra>"
            )
        ), row=1, col=2
    )

    # Bar 1: SOC Durations
    if parsed_soc:
        y_soc_total = [a + b for a, b in zip(y_soc_auth, y_soc_build)]
        max_duration = max(y_soc_total) if y_soc_total else 20

        fig.add_trace(go.Bar(
            x=x_soc, y=y_soc_auth, name="Permit to Start",
            marker_color="#F6B26B",
            hovertemplate=(
                "%{x[0]} - %{x[1]}<br>"
                "<b>Permit to Start:</b> %{y} Months<extra></extra>"
            ),
            legend="legend2"
        ), row=2, col=1)

        fig.add_trace(go.Bar(
            x=x_soc, y=y_soc_build, name="Start to Completion",
            marker_color="#3D85C6",
            text=[f"{val:.1f}" for val in y_soc_total],
            textposition="outside", textfont=dict(size=10, color="black"),
            hovertemplate=(
                "%{x[0]} - %{x[1]}<br>"
                "<b>Start to Completion:</b> %{y} Months<extra></extra>"
            ),
            legend="legend2"
        ), row=2, col=1)

    # Bar 2: Costs Breakdown (NAHB Traces)
    colors_nahb_high = {'Total Const. Costs': '#E57373', 'Non-Const. Costs': '#64B5F6'}
    for _, row in df1.iterrows():
        fig.add_trace(go.Bar(
            x=[row['Percent']], y=['High Level'], name=row['LegendLabel'],
            orientation='h',
            marker=dict(color=colors_nahb_high.get(row['Label'], '#E57373')),
            legendgroup='High Level',
            hovertemplate=(
                f"<b>{row['Label']}</b><br>"
                f"Cost: ${row['Cost']/1000:.0f}K<br>"
                f"Share: {row['Percent']:.1f}%<extra></extra>"
            ),
            legend="legend", visible=True
        ), row=2, col=2)

    for _, row in df2_sorted.iterrows():
        fig.add_trace(go.Bar(
            x=[row['Percent']], y=['Detailed'], name=row['LegendLabel'],
            orientation='h', marker=dict(color=row['Color']),
            legendgroup='Detailed Breakdown',
            hovertemplate=(
                f"<b>{row['Label']}</b><br>"
                f"Cost: ${row['Cost']/1000:.0f}K<br>"
                f"Share: {row['Percent']:.1f}%<extra></extra>"
            ),
            legend="legend", visible=True
        ), row=2, col=2)

    # Bar 2: Costs Breakdown (Terner Center Traces - Default Hidden)
    colors_terner_high = {
        'Hard Costs': '#E57373', 'Soft Costs': '#64B5F6',
        'Land Acquisition': '#81C784'
    }
    for _, row in terner_high.iterrows():
        fig.add_trace(go.Bar(
            x=[row['Percent']], y=['High Level'], name=row['LegendLabel'],
            orientation='h',
            marker=dict(color=colors_terner_high.get(row['Label'])),
            legendgroup='High Level',
            hovertemplate=(
                f"<b>{row['Label']}</b><br>"
                f"Share: {row['Percent']:.1f}%<extra></extra>"
            ),
            legend="legend", visible=False
        ), row=2, col=2)

    for _, row in terner_det.iterrows():
        fig.add_trace(go.Bar(
            x=[row['Percent']], y=['Detailed'], name=row['LegendLabel'],
            orientation='h', marker=dict(color=row['Color']),
            legendgroup='Detailed Breakdown',
            hovertemplate=(
                f"<b>{row['Label']}</b><br>"
                f"Share: {row['Percent']:.1f}%<extra></extra>"
            ),
            legend="legend", visible=False
        ), row=2, col=2)

    # -------------------------------------------------------------
    # LAYOUT, DOMAINS & TOGGLE MENUS
    # -------------------------------------------------------------

    # Calculate trace indices for toggle buttons
    base_traces = 4  # 2 maps, 2 soc duration bars
    nahb_traces = len(df1) + len(df2_sorted)
    terner_traces = len(terner_high) + len(terner_det)

    show_nahb = (
        [True] * base_traces + [True] * nahb_traces + [False] * terner_traces
    )
    show_terner = (
        [True] * base_traces + [False] * nahb_traces + [True] * terner_traces
    )

    fig.update_layout(
        dragmode="pan",
        height=1400, barmode='stack',
        geo=dict(scope='usa', projection_type='albers usa'),
        geo2=dict(scope='usa', projection_type='albers usa'),
        margin={"r": 0, "t": 60, "l": 0, "b": 150},
        updatemenus=[
            dict(
                type="buttons",
                direction="down",
                x=0.98, y=0.41,
                xanchor="right", yanchor="bottom",
                buttons=list([
                    dict(
                        label="Single-Family (NAHB)",
                        method="update",
                        args=[
                            {"visible": show_nahb},
                            {"annotations[3].text": (
                                "Cost Breakdown: Single-Family<br><sup>Source: "
                                "NAHB (2024)</sup>")}
                        ]
                    ),
                    dict(
                        label="Multi-Family (Terner)",
                        method="update",
                        args=[
                            {"visible": show_terner},
                            {"annotations[3].text": (
                                "Cost Breakdown: Multi-Family<br><sup>Source: "
                                "Terner Center (2023)</sup>")}
                        ]
                    )
                ]),
                showactive=True,
                bgcolor="white", bordercolor="gray", borderwidth=1
            )
        ],
        legend=dict(
            orientation="v", yanchor="top", y=-0.06, xanchor="center", x=0.79,
            groupclick="toggleitem", title_text="<b>Cost Components</b>"
        ),
        legend2=dict(
            orientation="v", yanchor="top", y=-0.06, xanchor="center", x=0.30,
            title_text="<b>Build Phase</b>"
        )
    )

    fig.update_yaxes(
        categoryorder='array', categoryarray=['Detailed', 'High Level'],
        ticksuffix="&nbsp;&nbsp;&nbsp;&nbsp;", row=2, col=2
    )

    fig.update_xaxes(domain=[0.15, 0.45], tickangle=0, row=2, col=1)
    # Ensure cost bars map strictly from 0 to 100% horizontally
    fig.update_xaxes(
        domain=[0.60, 0.98], range=[0, 100], title_text="% of Total Cost", 
        row=2, col=2
    )

    fig.update_yaxes(
        title_text="Total Duration (Months)", dtick=4,
        range=[0, max_duration * 1.15] if parsed_soc else None, row=2, col=1
    )

    annotations = list(fig.layout.annotations)
    annotations[2].x = 0.30
    annotations[3].x = 0.79
    fig.update_layout(annotations=annotations)

    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    html_maps_path = f"{output_dir}/permits_construction_costs.html"
    fig.write_html(
        html_maps_path, default_width='95%', default_height='100%',
        config={'scrollZoom': True}
    )
    print(f" -> Success! Construction HTML saved to {html_maps_path}")


def plot_county_heating_equipment(census_key, output_dir):
    """Electric heating penetration and shift to/from electric heating fuel."""
    print("Plotting: County-Level heating equipment (Census ACS)...")

    geojson_url = (
        'https://raw.githubusercontent.com/plotly/datasets/master/'
        'geojson-counties-fips.json'
    )
    try:
        with urlopen(geojson_url) as response:
            counties = json.load(response)
    except Exception as e:
        print(f"\n[WARNING] Failed to download county GeoJSON. Error: {e}")
        return

    def get_heating_data(year):
        url = f"https://api.census.gov/data/{year}/acs/acs5"
        params = {
            "get": "NAME,B25040_001E,B25040_004E",
            "for": "county:*", "key": census_key
        }
        resp = requests.get(url, params=params, timeout=20)
        if resp.status_code != 200:
            print(f" -> [WARNING] Failed to fetch ACS data for {year}. "
                  f"Status: {resp.status_code}")
            return None

        data = resp.json()
        df = pd.DataFrame(data[1:], columns=data[0])
        df['FIPS'] = df['state'].str.zfill(2) + df['county'].str.zfill(3)
        df['Total_HH'] = pd.to_numeric(
            df['B25040_001E'], errors='coerce'
        ).fillna(0)
        df['Electric_HH'] = pd.to_numeric(
            df['B25040_004E'], errors='coerce'
        ).fillna(0)

        mask = (pd.to_numeric(df['state'], errors='coerce') < 60) & \
               (df['Total_HH'] > 0)
        return df[mask][['FIPS', 'NAME', 'Total_HH', 'Electric_HH']].copy()

    curr_year = pd.Timestamp.now().year
    df_latest = None
    while curr_year >= 2020:
        df_latest = get_heating_data(curr_year)
        if df_latest is not None:
            latest_yr = curr_year
            break
        curr_year -= 1

    if df_latest is None:
        print("\n[WARNING] Could not fetch latest ACS data. Skipping map.")
        return

    base_year = latest_yr - 4
    print(f" -> Comparing {latest_yr} vs {base_year}...")
    df_prev = get_heating_data(base_year)

    if df_prev is None or df_latest is None:
        print("\n[WARNING] Could not complete API calls. Skipping map.")
        return

    ct_crosswalk = {
        '09110': '09003', '09120': '09001', '09130': '09007',
        '09140': '09009', '09150': '09015', '09160': '09005',
        '09170': '09009', '09180': '09011', '09190': '09001'
    }
    df_latest['FIPS'] = df_latest['FIPS'].replace(ct_crosswalk)
    df_latest = df_latest.groupby('FIPS', as_index=False).agg({
        'NAME': 'first', 'Total_HH': 'sum', 'Electric_HH': 'sum'
    })

    df_merged = pd.merge(
        df_prev, df_latest, on='FIPS', suffixes=('_20', '_24'), how='inner'
    )

    df_merged['Pct_Electric_20'] = (
        df_merged['Electric_HH_20'] / df_merged['Total_HH_20']
    ) * 100
    df_merged['Pct_Electric_24'] = (
        df_merged['Electric_HH_24'] / df_merged['Total_HH_24']
    ) * 100
    df_merged['Shift_Pct'] = (
        df_merged['Pct_Electric_24'] - df_merged['Pct_Electric_20']
    )

    abs_max = max(
        abs(df_merged['Shift_Pct'].quantile(0.02)),
        abs(df_merged['Shift_Pct'].quantile(0.98))
    )

    fig_maps = make_subplots(
        rows=1, cols=2, horizontal_spacing=0.05,
        specs=[[{'type': 'choropleth'}, {'type': 'choropleth'}]],
        subplot_titles=(
            f"Electric Heat Penetration, {latest_yr}<br>"
            "<sup>Source: Census ACS (Residential)</sup>",
            f"Electric Shift, {latest_yr} vs. {base_year}"
            "<br><sup>Source: Census ACS (Residential)</sup>"
        )
    )

    fig_maps.add_trace(
        go.Choropleth(
            geojson=counties, locations=df_merged['FIPS'],
            z=df_merged['Pct_Electric_24'], colorscale="Viridis",
            zmin=0, zmax=100, marker_line_width=0,
            colorbar=dict(title="%", x=0.46, len=0.75),
            customdata=df_merged[['NAME_24', 'Pct_Electric_20']],
            hovertemplate=(
                "<b>%{customdata[0]}</b><br>2020 Base: %{customdata[1]:.1f}%"
                "<br>2024 Base: <b>%{z:.1f}%</b><extra></extra>"
            )
        ), row=1, col=1
    )

    fig_maps.add_trace(
        go.Choropleth(
            geojson=counties, locations=df_merged['FIPS'],
            z=df_merged['Shift_Pct'], colorscale="RdBu",
            zmin=-abs_max, zmax=abs_max, marker_line_width=0,
            colorbar=dict(title="%", x=1.02, len=0.75),
            customdata=df_merged[
                ['NAME_24', 'Pct_Electric_20', 'Pct_Electric_24']
            ],
            hovertemplate=(
                "<b>%{customdata[0]}</b><br>2020 Base: %{customdata[1]:.1f}%"
                "<br>2024 Base: %{customdata[2]:.1f}%<br>"
                "Net Shift: <b>%{z:+.2f}%</b><extra></extra>"
            )
        ), row=1, col=2
    )

    annotations = list(fig_maps.layout.annotations)
    annotations[0].yshift = -20
    annotations[1].yshift = -20
    fig_maps.layout.annotations = annotations

    fig_maps.update_layout(
        dragmode="pan",
        geo=dict(scope='usa', projection_type='albers usa'),
        geo2=dict(scope='usa', projection_type='albers usa'),
        margin={"r": 0, "t": 60, "l": 0, "b": 0}, height=700
    )

    html_path = f"{output_dir}/heating_equip_map.html"
    fig_maps.write_html(
        html_path, default_width='100%', default_height='100%',
        config={'scrollZoom': True}
    )
    print(f" -> Success! Heating equipment map HTML saved to {html_path}")


def plot_ann_elec_sales(output_dir):
    """Annual electricity demand and change over time."""
    print("Plotting: Annual electricity demand growth (EIA 861)...")

    state_centroids = {
        'AL': (32.8, -86.7), 'AK': (61.3, -152.4), 'AZ': (33.7, -111.4),
        'AR': (34.9, -92.3), 'CA': (36.1, -119.6), 'CO': (39.0, -105.3),
        'CT': (41.5, -72.7), 'DE': (39.3, -75.5), 'FL': (27.7, -81.6),
        'GA': (33.0, -83.6), 'HI': (21.0, -157.4), 'ID': (44.2, -114.4),
        'IL': (40.3, -88.9), 'IN': (39.8, -86.2), 'IA': (42.0, -93.2),
        'KS': (38.5, -96.7), 'KY': (37.6, -84.6), 'LA': (31.1, -91.8),
        'ME': (44.6, -69.3), 'MD': (39.0, -76.8), 'MA': (42.2, -71.5),
        'MI': (43.3, -84.5), 'MN': (45.6, -93.9), 'MS': (32.7, -89.6),
        'MO': (38.4, -92.2), 'MT': (46.9, -110.4), 'NE': (41.1, -98.2),
        'NV': (38.3, -117.0), 'NH': (43.4, -71.5), 'NJ': (40.2, -74.5),
        'NM': (34.8, -106.2), 'NY': (42.1, -74.9), 'NC': (35.6, -79.8),
        'ND': (47.5, -99.7), 'OH': (40.3, -82.7), 'OK': (35.5, -96.9),
        'OR': (44.5, -122.0), 'PA': (40.5, -77.2), 'RI': (41.6, -71.5),
        'SC': (33.8, -80.9), 'SD': (44.2, -99.4), 'TN': (35.7, -86.6),
        'TX': (31.0, -97.5), 'UT': (40.1, -111.8), 'VT': (44.0, -72.7),
        'VA': (37.7, -78.1), 'WA': (47.4, -121.4), 'WV': (38.4, -80.9),
        'WI': (44.2, -89.6), 'WY': (42.7, -107.3), 'DC': (38.9, -77.0)
    }

    def extract_sales_data(year):
        urls = [
            f"https://www.eia.gov/electricity/data/eia861/zip/f861{year}.zip",
            ("https://www.eia.gov/electricity/data/eia861/archive/zip/"
             f"f861{year}.zip")
        ]
        headers = {'User-Agent': 'Mozilla/5.0'}
        r = None
        for url in urls:
            try:
                temp_r = requests.get(url, headers=headers, timeout=60)
                if temp_r.status_code == 200 and temp_r.content.startswith(b'PK'):
                    r = temp_r
                    break
            except Exception:
                pass

        if r is None:
            return None

        try:
            with zipfile.ZipFile(io.BytesIO(r.content)) as z:
                target = next(
                    (f for f in z.namelist() if 'sales_ult_cust' in f.lower()
                     and not f.startswith('~')), None
                )
                if not target:
                    return None

                df = pd.read_excel(z.open(target), header=None)
                mask = df.apply(
                    lambda row: row.astype(str).str.contains(
                        'Utility Number|Utility ID', case=False, na=False
                    ).any(), axis=1
                )
                header_idx = mask.index[mask][0]

                super_row_idx = -1
                for i in range(header_idx, -1, -1):
                    if df.iloc[i].astype(str).str.contains(
                            'RESIDENTIAL', case=False, na=False).any():
                        super_row_idx = i
                        break

                if super_row_idx != -1:
                    top_row = df.iloc[super_row_idx].astype(str).str.strip().\
                        replace(['nan', 'None', ''], pd.NA).ffill().fillna('')
                    bottom_row = df.iloc[header_idx].astype(str).str.strip().\
                        replace(['nan', 'None'], '')
                    combined_cols = top_row + "_" + bottom_row
                else:
                    combined_cols = df.iloc[header_idx].astype(str).replace(
                        'nan', ''
                    )

                df.columns = combined_cols.str.lower().str.replace('\n', ' ')
                df = df.iloc[header_idx + 1:].reset_index(drop=True)

                def get_col(keywords, exclude=None):
                    for c in df.columns:
                        if all(k in str(c) for k in keywords):
                            if exclude and any(ex in str(c) for ex in exclude):
                                continue
                            return c
                    return None

                cols_map = {
                    'Utility_Num': get_col(['utility', 'number']) or
                    get_col(['utility', 'id']),
                    'Utility_Name': get_col(['utility', 'name']),
                    'State': get_col(['state'], exclude=['rate', 'code']),
                    'Res_Sales': get_col(['residential', 'megawatthours']),
                    'Com_Sales': get_col(['commercial', 'megawatthours']),
                    'Ind_Sales': get_col(['industrial', 'megawatthours']),
                    'Tra_Sales': get_col(['transportation', 'megawatthours'])
                }

                df = df[list(cols_map.values())].copy()
                df.columns = list(cols_map.keys())

                for s in ['Utility_Num', 'Res_Sales', 'Com_Sales',
                          'Ind_Sales', 'Tra_Sales']:
                    df[s] = pd.to_numeric(df[s], errors='coerce').fillna(0)

                return df.groupby(
                    ['Utility_Num', 'Utility_Name', 'State'], as_index=False
                ).agg({
                    'Res_Sales': 'sum', 'Com_Sales': 'sum',
                    'Ind_Sales': 'sum', 'Tra_Sales': 'sum'
                })
        except Exception as e:
            print(f"Error: {e}")
            return None

    latest_yr = find_latest_eia_861_year()
    year_mid = latest_yr - 2
    base_year = latest_yr - 5

    latest_yr_suff, year_mid_suff, base_year_suff = [
        str(x)[-2:] for x in [latest_yr, year_mid, base_year]
    ]

    print(f" -> Fetching EIA-861 for {latest_yr}, {year_mid}, {base_year}...")
    df_latest = extract_sales_data(latest_yr)
    df_mid = extract_sales_data(year_mid)
    df_base = extract_sales_data(base_year)

    if any(df is None for df in [df_latest, df_mid, df_base]):
        return

    def rename_for_year(df, suffix):
        cols_to_rename = ['Res_Sales', 'Com_Sales', 'Ind_Sales', 'Tra_Sales']
        rename_map = {c: f"{c}_{suffix}" for c in cols_to_rename}
        return df.rename(columns=rename_map)

    df_base_renamed = rename_for_year(df_base, base_year_suff)
    df_mid_renamed = rename_for_year(df_mid, year_mid_suff)
    df_latest_renamed = rename_for_year(df_latest, latest_yr_suff)

    df_m = pd.merge(
        df_base_renamed, df_mid_renamed, on=['Utility_Num', 'State']
    )
    df_m = pd.merge(df_m, df_latest_renamed, on=['Utility_Num', 'State'])

    if 'Utility_Name' in df_m.columns:
        df_m = df_m.rename(
            columns={'Utility_Name': f'Utility_Name_{latest_yr_suff}'}
        )

    for y in [base_year_suff, year_mid_suff, latest_yr_suff]:
        cols = [f'Res_Sales_{y}', f'Com_Sales_{y}',
                f'Ind_Sales_{y}', f'Tra_Sales_{y}']
        df_m[f'Total_{y}'] = df_m[cols].sum(axis=1)

    agg_map = {
        f'Total_{base_year_suff}': 'sum',
        f'Total_{year_mid_suff}': 'sum',
        f'Total_{latest_yr_suff}': 'sum',
        f'Res_Sales_{latest_yr_suff}': 'sum',
        f'Com_Sales_{latest_yr_suff}': 'sum',
        f'Ind_Sales_{latest_yr_suff}': 'sum',
        f'Tra_Sales_{latest_yr_suff}': 'sum',
        f'Res_Sales_{base_year_suff}': 'sum',
        f'Com_Sales_{base_year_suff}': 'sum',
        f'Ind_Sales_{base_year_suff}': 'sum',
        f'Tra_Sales_{base_year_suff}': 'sum'
    }
    state_all = df_m.groupby('State').agg(agg_map).reset_index()

    state_all['State_5yr'] = (
        (state_all[f'Total_{latest_yr_suff}'] -
         state_all[f'Total_{base_year_suff}']) /
        (state_all[f'Total_{base_year_suff}'] + 1)
    ) * 100
    state_all['State_2yr'] = (
        (state_all[f'Total_{latest_yr_suff}'] -
         state_all[f'Total_{year_mid_suff}']) /
        (state_all[f'Total_{year_mid_suff}'] + 1)
    ) * 100

    for s in ['Res', 'Com', 'Ind', 'Tra']:
        state_all[f'{s}_Contrib'] = (
            (state_all[f'{s}_Sales_{latest_yr_suff}'] -
             state_all[f'{s}_Sales_{base_year_suff}']) /
            (state_all[f'Total_{base_year_suff}'] + 1)
        ) * 100

    df_leaders = df_m.sort_values(
        ['State', f'Total_{latest_yr_suff}'], ascending=[True, False]
    ).groupby('State').head(1).copy()

    df_leaders['Util_5yr'] = (
        (df_leaders[f'Total_{latest_yr_suff}'] -
         df_leaders[f'Total_{base_year_suff}']) /
        (df_leaders[f'Total_{base_year_suff}'] + 1)
    ) * 100
    df_leaders['Util_2yr'] = (
        (df_leaders[f'Total_{latest_yr_suff}'] -
         df_leaders[f'Total_{year_mid_suff}']) /
        (df_leaders[f'Total_{year_mid_suff}'] + 1)
    ) * 100

    df_leaders_sub = df_leaders[[
        'State', f'Utility_Name_{latest_yr_suff}', 'Util_5yr', 'Util_2yr',
        f'Total_{latest_yr_suff}'
    ]].rename(
        columns={f'Total_{latest_yr_suff}': f'Leader_Total_{latest_yr_suff}'}
    )

    df_plot = pd.merge(state_all, df_leaders_sub, on='State')

    def apply_loc(row):
        st = str(row['State']).upper().strip()
        if st in state_centroids:
            return pd.Series({
                'Lat': state_centroids[st][0],
                'Lon': state_centroids[st][1]
            })
        return pd.Series({'Lat': None, 'Lon': None})

    df_plot[['Lat', 'Lon']] = df_plot.apply(apply_loc, axis=1).dropna()

    def make_hover(row):
        line1 = f"<b>STATE: {row['State']}</b><br>"
        line2 = f"Total Sales: {row[('Total_' + latest_yr_suff)]:,.0f} MWh<br>"
        line3 = f"State 5-yr Growth: <b>{row['State_5yr']:+.1f}%</b><br>"
        line4 = f"State 2-yr Growth: <b>{row['State_2yr']:+.1f}%</b><br>---<br>"
        line5 = f"Market Leader: {row[('Utility_Name_' + latest_yr_suff)]}<br>"
        line6 = f"Leader 5-yr Growth: <b>{row['Util_5yr']:+.1f}%</b><br>"
        line7 = f"Leader 2-yr Growth: <b>{row['Util_2yr']:+.1f}%</b>"
        return f"{line1}{line2}{line3}{line4}{line5}{line6}{line7}"

    df_plot['HoverText'] = df_plot.apply(make_hover, axis=1)

    fig = make_subplots(
        rows=2, cols=1, row_heights=[0.6, 0.4], vertical_spacing=0.1,
        specs=[[{'type': 'scattergeo'}], [{'type': 'bar'}]],
        horizontal_spacing=0.05,
        subplot_titles=(
            f"Annual Electricity Sales by State, {latest_yr}, and Growth, "
            f"{base_year}-{latest_yr}<br><sup>Source: EIA 861</sup>",
            f"Highest Sales Growth States by Sector, {base_year}-{latest_yr}"
            "<br><sup>Source: EIA 861</sup>"
        )
    )

    sizeref = 2. * df_plot[('Total_' + latest_yr_suff)].max() / (65 ** 2)
    fig.add_trace(go.Scattergeo(
        lon=df_plot['Lon'], lat=df_plot['Lat'], text=df_plot['HoverText'],
        hoverinfo='text', showlegend=False,
        marker=dict(
            size=df_plot[('Total_' + latest_yr_suff)], sizemode='area',
            sizeref=sizeref, color=df_plot['State_5yr'], colorscale='RdBu',
            cmin=-20, cmax=20, showscale=True,
            colorbar=dict(title="5-yr Growth %", x=0.9, len=0.5, y=0.75)
        )
    ), row=1, col=1)

    state_sorted = state_all.sort_values('State_5yr', ascending=False).head(20)
    colors = {
        'Res': '#1f77b4', 'Com': '#ff7f0e', 'Ind': '#2ca02c', 'Tra': '#d62728'
    }
    sectors = [
        ('Res', 'Residential'), ('Com', 'Commercial'),
        ('Ind', 'Industrial'), ('Tra', 'Transportation')
    ]

    for s, name in sectors:
        fig.add_trace(go.Bar(
            name=name, x=state_sorted['State'],
            y=state_sorted[f'{s}_Contrib'], marker_color=colors[s]
        ), row=2, col=1)

    fig.add_trace(go.Scatter(
        name='Net 5-yr Growth %', x=state_sorted['State'],
        y=state_sorted['State_5yr'], mode='markers',
        marker=dict(color='black', size=10, symbol='diamond', line_width=1)
    ), row=2, col=1)

    fig.update_layout(
        dragmode="pan",
        barmode='relative', hovermode='x unified', height=1100,
        geo=dict(
            scope='usa', projection_type='albers usa', showland=True,
            landcolor='rgb(220, 220, 220)'
        ),
        legend=dict(
            orientation="h", yanchor="bottom", y=-0.1, xanchor="center", x=0.5
        )
    )

    fig.update_yaxes(title_text="% 5-yr Growth", row=2, col=1)

    html_path = f"{output_dir}/annual_sales.html"
    fig.write_html(
        html_path, default_width='100%', default_height='100%',
        config={'scrollZoom': True}
    )
    print(f" -> Success! Annual sales plots saved to {html_path}")


def extract_peak_data(year):
    """Targets Operational_Data and flattens multi-row headers."""
    urls = [
        f"https://www.eia.gov/electricity/data/eia861/zip/f861{year}.zip",
        ("https://www.eia.gov/electricity/data/eia861/archive/zip/"
         f"f861{year}.zip")
    ]
    headers = {'User-Agent': 'Mozilla/5.0'}
    r = None
    for url in urls:
        try:
            resp = requests.get(url, headers=headers, timeout=30)
            if resp.status_code == 200 and resp.content.startswith(b'PK'):
                r = resp
                break
        except Exception:
            continue
    if r is None:
        return None

    try:
        with zipfile.ZipFile(io.BytesIO(r.content)) as z:
            target = next(
                (f for f in z.namelist() if 'operational_data' in f.lower()
                 and not f.startswith('~')), None
            )
            if not target:
                target = next(
                    (f for f in z.namelist() if 'utility_data' in f.lower()
                     and not f.startswith('~')), None
                )
            if not target:
                return None

            df_top = pd.read_excel(z.open(target), header=None, nrows=15)
            mask = df_top.apply(
                lambda row: row.astype(str).str.contains(
                    'Utility Number|Utility ID|Data Year', case=False, na=False
                ).any(), axis=1
            )
            header_start = mask.idxmax()

            df_h = pd.read_excel(
                z.open(target), header=None, skiprows=header_start, nrows=3
            )
            df_h.iloc[0] = df_h.iloc[0].ffill()

            flat_cols = []
            for col_idx in range(len(df_h.columns)):
                combined = "_".join(
                    df_h.iloc[:, col_idx].astype(str).replace('nan', '')
                    .str.lower().str.strip()
                )
                flat_cols.append(combined)

            df_raw = pd.read_excel(
                z.open(target), skiprows=header_start + 3, header=None
            )
            df_raw.columns = flat_cols

            def find_idx(keys):
                for i, h in enumerate(flat_cols):
                    if all(k in h for k in keys):
                        return i
                return None

            idx_uid = find_idx(['utility', 'number']) or find_idx(
                ['utility', 'id']
            )
            idx_st = find_idx(['state'])
            idx_sum = find_idx(['summer', 'peak']) or find_idx(
                ['summer', 'demand']
            ) or find_idx(['summer', 'max'])
            idx_win = find_idx(['winter', 'peak']) or find_idx(
                ['winter', 'demand']
            ) or find_idx(['winter', 'max'])

            if None in [idx_uid, idx_st, idx_sum, idx_win]:
                return None

            res_df = pd.DataFrame({
                'Util_ID': df_raw.iloc[:, idx_uid],
                'State': df_raw.iloc[:, idx_st],
                'Summer_MW': pd.to_numeric(
                    df_raw.iloc[:, idx_sum], errors='coerce'
                ).fillna(0),
                'Winter_MW': pd.to_numeric(
                    df_raw.iloc[:, idx_win], errors='coerce'
                ).fillna(0)
            })
            return res_df.dropna(subset=['Util_ID'])
    except Exception as e:
        print(f"Error: {e}")
        return None


def plot_peak_data(output_dir):
    """Peak electricity demand and change over time."""
    print("Plotting: Peak demand growth (EIA 861))...")

    state_centroids = {
        'AL': (32.8066, -86.7911), 'AK': (61.3707, -152.4044),
        'AZ': (33.7297, -111.4312), 'AR': (34.9697, -92.3731),
        'CA': (36.1162, -119.6815), 'CO': (39.0598, -105.3111),
        'CT': (41.5977, -72.7553), 'DE': (39.3185, -75.5071),
        'FL': (27.7662, -81.6867), 'GA': (33.0406, -83.6430),
        'HI': (21.0943, -157.4983), 'ID': (44.2404, -114.4788),
        'IL': (40.3494, -88.9861), 'IN': (39.8494, -86.2582),
        'IA': (42.0115, -93.2105), 'KS': (38.5266, -96.7264),
        'KY': (37.6681, -84.6700), 'LA': (31.1695, -91.8678),
        'ME': (44.6939, -69.3819), 'MD': (39.0639, -76.8021),
        'MA': (42.2301, -71.5301), 'MI': (43.3266, -84.5361),
        'MN': (45.6944, -93.9001), 'MS': (32.7416, -89.6786),
        'MO': (38.4560, -92.2883), 'MT': (46.9219, -110.4543),
        'NE': (41.1253, -98.2680), 'NV': (38.3135, -117.0553),
        'NH': (43.4524, -71.5638), 'NJ': (40.2989, -74.5210),
        'NM': (34.8405, -106.2484), 'NY': (42.1657, -74.9480),
        'NC': (35.6300, -79.8064), 'ND': (47.5289, -99.7840),
        'OH': (40.3887, -82.7649), 'OK': (35.5653, -96.9289),
        'OR': (44.5720, -122.0709), 'PA': (40.5907, -77.2097),
        'RI': (41.6808, -71.5117), 'SC': (33.8568, -80.9450),
        'SD': (44.2998, -99.4388), 'TN': (35.7478, -86.6923),
        'TX': (31.0544, -97.5634), 'UT': (40.1500, -111.8624),
        'VT': (44.0458, -72.7106), 'VA': (37.7693, -78.1699),
        'WA': (47.4009, -121.4904), 'WV': (38.4912, -80.9544),
        'WI': (44.2685, -89.6165), 'WY': (42.7560, -107.3024),
        'DC': (38.9071, -77.0368)
    }

    latest_yr = find_latest_eia_861_year()
    base_year = latest_yr - 5

    latest_yr_suff, base_year_suff = [
        str(x)[-2:] for x in [latest_yr, base_year]
    ]

    print(f" -> Comparing Peak Data: {latest_yr} vs {base_year}...")
    df_latest = extract_peak_data(latest_yr)
    df_base = extract_peak_data(base_year)
    if df_latest is None or df_base is None:
        return

    def rename_peak_cols(df, suffix):
        return df.rename(columns={
            'Summer_MW': f'Summer_MW_{suffix}',
            'Winter_MW': f'Winter_MW_{suffix}'
        })

    df_latest_renamed = rename_peak_cols(df_latest, latest_yr_suff)
    df_base_renamed = rename_peak_cols(df_base, base_year_suff)

    df_m = pd.merge(
        df_base_renamed, df_latest_renamed, on=['Util_ID', 'State']
    )
    valid_us_states = set(state_centroids.keys())

    st = df_m.groupby('State').agg({
        f'Summer_MW_{latest_yr_suff}': 'sum',
        f'Winter_MW_{latest_yr_suff}': 'sum',
        f'Summer_MW_{base_year_suff}': 'sum',
        f'Winter_MW_{base_year_suff}': 'sum'
    }).reset_index()

    st = st[st['State'].isin(valid_us_states)].copy()

    st['Ratio'] = (
        st[f'Summer_MW_{latest_yr_suff}'] /
        (st[f'Winter_MW_{latest_yr_suff}'] + 1)
    )
    st['Max_MW'] = st[
        [f'Summer_MW_{latest_yr_suff}', f'Winter_MW_{latest_yr_suff}']
    ].max(axis=1)

    st['Winter_Growth'] = (
        (st[f'Winter_MW_{latest_yr_suff}'] -
         st[f'Winter_MW_{base_year_suff}']) /
        (st[f'Winter_MW_{base_year_suff}'] + 1)
    ) * 100

    st['Summer_Growth'] = (
        (st[f'Summer_MW_{latest_yr_suff}'] -
         st[f'Summer_MW_{base_year_suff}']) /
        (st[f'Summer_MW_{base_year_suff}'] + 1)
    ) * 100

    fig = make_subplots(
        rows=2, cols=2,
        row_heights=[0.6, 0.4],
        vertical_spacing=0.12,
        horizontal_spacing=0.15,
        specs=[
            [{"type": "scattergeo", "colspan": 2}, None],
            [{"type": "bar"}, {"type": "bar"}]
        ],
        subplot_titles=(
            f"Peak Demand Seasonality, {latest_yr}<br>"
            "<sup>Source: EIA 861</sup>",
            f"Highest Winter Peak Growth, {base_year}-{latest_yr}<br>"
            "<sup>Source: EIA</sup>",
            f"Highest Summer Peak Growth, {base_year}-{latest_yr}<br>"
            "<sup>Source: EIA</sup>"
        )
    )

    sizeref = 2. * st['Max_MW'].max() / (60 ** 2)
    lats = st['State'].map(lambda x: state_centroids[x][0])
    lons = st['State'].map(lambda x: state_centroids[x][1])

    hover_text = (
        st['State'] + "<br>Max Peak: " +
        st['Max_MW'].apply(lambda x: f"{x:,.0f} MW") +
        "<br>Ratio: " + st['Ratio'].round(2).astype(str)
    )

    fig.add_trace(go.Scattergeo(
        lon=lons, lat=lats,
        marker=dict(
            size=st['Max_MW'], sizemode='area', sizeref=sizeref,
            color=st['Ratio'], colorscale='RdYlBu_r', cmin=0.8, cmid=1.0,
            cmax=1.2, showscale=True,
            colorbar=dict(
                title="Summer/Winter<br>Peak Ratio", thickness=15, len=0.4,
                y=0.8, x=0.95
            )
        ),
        text=hover_text, hoverinfo='text', showlegend=False
    ), row=1, col=1)

    st_winter = st.sort_values('Winter_Growth', ascending=False).head(15)
    fig.add_trace(go.Bar(
        x=st_winter['State'], y=st_winter['Winter_Growth'],
        marker_color='#1f77b4', name='Winter Growth',
        hovertemplate=(
            "State: %{x}<br>Winter Growth: %{y:+.1f}%<extra></extra>"
        )
    ), row=2, col=1)

    st_summer = st.sort_values('Summer_Growth', ascending=False).head(15)
    fig.add_trace(go.Bar(
        x=st_summer['State'], y=st_summer['Summer_Growth'],
        marker_color='#ff7f0e', name='Summer Growth',
        hovertemplate=(
            "State: %{x}<br>Summer Growth: %{y:+.1f}%<extra></extra>"
        )
    ), row=2, col=2)

    fig.update_layout(
        dragmode="pan",
        height=1000, margin={"r": 30, "t": 80, "l": 30, "b": 50},
        showlegend=False,
        geo=dict(
            scope='usa', projection_type='albers usa', showland=True,
            landcolor='rgb(220, 220, 220)'
        )
    )

    fig.update_xaxes(domain=[0.05, 0.45], row=2, col=1)
    fig.update_xaxes(domain=[0.55, 0.95], row=2, col=2)

    annotations = list(fig.layout.annotations)
    annotations[1].x = 0.25
    annotations[2].x = 0.75
    fig.update_layout(annotations=annotations)

    fig.update_yaxes(title_text="5-Year Growth (%)", row=2, col=1)
    fig.update_yaxes(title_text="5-Year Growth (%)", row=2, col=2)

    html_path = f"{output_dir}/peak_demand.html"
    fig.write_html(
        html_path, default_width='100%', default_height='100%',
        config={'scrollZoom': True}
    )
    print(f" -> Success! Peak demand plots saved to {html_path}")


def generate_eia_mapping_df(year):
    """Fetches EIA-861 master Utility-to-State mapping."""
    base_urls = [
        f"https://www.eia.gov/electricity/data/eia861/zip/f861{year}.zip",
        ("https://www.eia.gov/electricity/data/eia861/archive/zip/"
         f"f861{year}.zip")
    ]
    headers = {'User-Agent': 'Mozilla/5.0'}
    valid_content = None

    for url in base_urls:
        try:
            r = requests.get(url, headers=headers, timeout=30)
            if r.status_code == 200 and r.content.startswith(b'PK'):
                valid_content = r.content
                break
        except Exception:
            continue
    if not valid_content:
        return None

    try:
        with zipfile.ZipFile(io.BytesIO(valid_content)) as z:
            target = next(
                (f for f in z.namelist() if 'sales_ult_cust' in f.lower()
                 and not f.startswith('~')), None
            )
            df_p = pd.read_excel(z.open(target), header=None, nrows=15)
            h_row = df_p[df_p.apply(
                lambda r: r.astype(str).str.contains(
                    'Utility ID|Utility Number', case=False).any(), axis=1
            )].index[0]
            df = pd.read_excel(z.open(target), skiprows=h_row)
            df.columns = [str(c).strip() for c in df.columns]
            col_id = next(
                c for c in df.columns if 'utility' in c.lower()
                and ('id' in c.lower() or 'number' in c.lower())
            )
            col_st = next(
                c for c in df.columns if 'state' in c.lower()
                and 'rate' not in c.lower()
            )
            eia_df = df[[col_id, col_st]].copy()
            eia_df.columns = ['Utility ID', 'State']
            eia_df['Utility ID'] = pd.to_numeric(
                eia_df['Utility ID'], errors='coerce'
            )
            return eia_df.dropna(subset=['Utility ID']).drop_duplicates()
    except Exception:
        return None


def get_functional_mapping():
    """Returns a dictionary mapping every FERC expense_type to a pillar."""
    gen = [
        'generation', 'power_production', 'fuel', 'nuclear', 'steam',
        'hydraulic', 'boiler', 'reactor', 'coolants', 'water_for_power',
        'generating_and_electric_plant', 'generation_interconnection'
    ]
    trans = [
        'transmission', 'load_dispatch', 'scheduling_system_control',
        'reliability_planning', 'ancillary_services',
        'market_administration', 'market_facilitation', 'market_monitoring'
    ]
    dist = [
        'distribution', 'line_transformers', 'meters', 'street_lighting',
        'customer_installations', 'station_expenses_distribution'
    ]
    other = [
        'administrative', 'customer_account', 'customer_records',
        'customer_service', 'advertising', 'selling', 'sales', 'pensions',
        'benefits', 'insurance', 'regulatory', 'uncollectible', 'franchise',
        'office_supplies', 'outside_services'
    ]
    return gen, trans, dist, other


def fetch_historical_om_ca(eia_df):
    """Fetches 10 years of utility O&M expenditure data, filtered for CA trend."""
    om_url = (
        "https://s3.us-west-2.amazonaws.com/pudl.catalyst.coop/nightly/"
        "core_ferc1__yearly_operating_expenses_sched320.parquet"
    )
    glue_url = (
        "https://raw.githubusercontent.com/catalyst-cooperative/pudl/main/"
        "src/pudl/package_data/glue/utility_id_pudl.csv"
    )

    try:
        df_om, df_glue = pd.read_parquet(om_url), pd.read_csv(glue_url)
        gen_k, trans_k, dist_k, other_k = get_functional_mapping()

        def apply_map(label):
            low = str(label).lower()
            if 'total' in low and 'generation' not in low and \
               'transmission' not in low and 'distribution' not in low:
                return None
            if any(k in low for k in gen_k):
                return 'Generation'
            if any(k in low for k in trans_k):
                return 'Transmission'
            if any(k in low for k in dist_k):
                return 'Distribution'
            return 'Other'

        df_om['pillar'] = df_om['expense_type'].apply(apply_map)
        df_om = df_om.dropna(subset=['pillar'])
        df_b = pd.merge(
            df_om, df_glue[['utility_id_ferc1', 'utility_id_eia']],
            on='utility_id_ferc1'
        )
        s_map = eia_df[['Utility ID', 'State']].drop_duplicates()
        df_f = pd.merge(
            df_b, s_map, left_on='utility_id_eia', right_on='Utility ID'
        )

        ly = df_f['report_year'].max()
        df_ly = df_f[df_f['report_year'] == ly]
        top_s = df_ly.pivot_table(
            index='State', columns='pillar', values='dollar_value',
            aggfunc='sum'
        ).fillna(0).reset_index()
        top_s['Total'] = top_s[
            ['Generation', 'Transmission', 'Distribution']
        ].sum(axis=1)
        top_s = top_s.sort_values('Total', ascending=False).head(15)

        df_ca = df_f[(df_f['State'] == 'CA') & (df_f['report_year'] >= 2015)]
        ca_t = df_ca.pivot_table(
            index='report_year', columns='pillar', values='dollar_value',
            aggfunc='sum'
        ).fillna(0).reset_index()

        for df in [top_s, ca_t]:
            for c in ['Generation', 'Transmission', 'Distribution']:
                if c in df.columns:
                    df[c] /= 1e9
        return top_s, ca_t, ly
    except Exception as e:
        print(f"Error: {e}")
        return None, None, None


def plot_utility_costs(year, output_dir):
    """Utility annual expenditures in generation, transmission, and distribution."""
    print("Plotting: Utility expenditures (FERC 1/PUDL)...")
    eia_df = generate_eia_mapping_df(year)
    top_s, ca_t, ly = fetch_historical_om_ca(eia_df)
    if top_s is None:
        return

    pillars = ['Generation', 'Transmission', 'Distribution']
    colors = {
        'Generation': '#1f77b4',
        'Transmission': '#ff7f0e',
        'Distribution': '#2ca02c'
    }

    fig = make_subplots(
        rows=2, cols=1, vertical_spacing=0.12, horizontal_spacing=0.05,
        subplot_titles=(
            f"Highest Utility O&M Costs, {ly}<br>"
            "<sup>Source: FERC Form 1</sup>",
            "CA 10-Year Utility O&M Cost Trend<br>"
            "<sup>Source: FERC Form 1 via PUDL</sup>"
        )
    )

    for cat in pillars:
        fig.add_trace(go.Bar(
            name=cat, x=top_s['State'], y=top_s[cat],
            marker_color=colors[cat], showlegend=True
        ), row=1, col=1)
        fig.add_trace(go.Bar(
            name=cat, x=ca_t['report_year'], y=ca_t[cat],
            marker_color=colors[cat], showlegend=False
        ), row=2, col=1)

    fig.update_layout(height=1000, barmode='stack', template="plotly_white")
    html_path = f"{output_dir}/utility_costs.html"
    fig.write_html(html_path, default_width='100%', default_height='100%')
    print(f" -> Success! Utility cost plots saved to {html_path}")


def fetch_dsm_detailed(year):
    """Fetches Total MW and Sector-level MW (Res, Com, Ind, Trans)."""
    base_urls = [
        f"https://www.eia.gov/electricity/data/eia861/zip/f861{year}.zip",
        ("https://www.eia.gov/electricity/data/eia861/archive/zip/"
         f"f861{year}.zip")
    ]
    headers = {'User-Agent': 'Mozilla/5.0'}

    valid_content = None
    for url in base_urls:
        try:
            r = requests.get(url, headers=headers, timeout=20)
            if r.status_code == 200 and r.content.startswith(b'PK'):
                valid_content = r.content
                break
        except Exception:
            continue

    if not valid_content:
        return None, None

    try:
        with zipfile.ZipFile(io.BytesIO(valid_content)) as z:
            ee_file = next(
                (f for f in z.namelist() if 'energy_efficiency' in f.lower()
                 and not f.startswith('~')), None
            )
            dr_file = next(
                (f for f in z.namelist() if 'demand_response' in f.lower()
                 and not f.startswith('~')), None
            )

            def extract_logic(f_name, suffix):
                if not f_name:
                    return None
                df_raw = pd.read_excel(z.open(f_name), header=None)
                data = df_raw.iloc[3:].copy()

                if suffix == 'EE':
                    return pd.DataFrame({
                        'Utility ID': data.iloc[:, 1],
                        'Utility': data.iloc[:, 2],
                        'State': data.iloc[:, 3],
                        'EE_Res': pd.to_numeric(
                            data.iloc[:, 10], errors='coerce').fillna(0),
                        'EE_Com': pd.to_numeric(
                            data.iloc[:, 11], errors='coerce').fillna(0),
                        'EE_Ind': pd.to_numeric(
                            data.iloc[:, 12], errors='coerce').fillna(0),
                        'EE_Trans': pd.to_numeric(
                            data.iloc[:, 13], errors='coerce').fillna(0),
                        'EE_Total': pd.to_numeric(
                            data.iloc[:, 14], errors='coerce').fillna(0)
                    })
                else:
                    return pd.DataFrame({
                        'Utility ID': data.iloc[:, 1],
                        'Utility': data.iloc[:, 2],
                        'State': data.iloc[:, 3],
                        'DR_Pot_Res': pd.to_numeric(
                            data.iloc[:, 15], errors='coerce').fillna(0),
                        'DR_Pot_Com': pd.to_numeric(
                            data.iloc[:, 16], errors='coerce').fillna(0),
                        'DR_Pot_Ind': pd.to_numeric(
                            data.iloc[:, 17], errors='coerce').fillna(0),
                        'DR_Pot_Trans': pd.to_numeric(
                            data.iloc[:, 18], errors='coerce').fillna(0),
                        'DR_Pot_Total': pd.to_numeric(
                            data.iloc[:, 19], errors='coerce').fillna(0),
                        'DR_Act_Total': pd.to_numeric(
                            data.iloc[:, 24], errors='coerce').fillna(0)
                    })
            return extract_logic(ee_file, 'EE'), extract_logic(dr_file, 'DR')
    except Exception as e:
        print(f" [!] Fetch Failed: {e}")
        return None, None


def get_dsm_snapshot(year):
    """Fetches 861 EE/DR data snapshots for given year and combines."""
    df_ee, df_dr = fetch_dsm_detailed(year)
    if df_ee is None or df_dr is None:
        return None

    df_combined = pd.merge(
        df_ee, df_dr, on=['Utility ID', 'State'], how='outer',
        suffixes=('', '_dr')
    )
    df_combined['Utility'] = df_combined['Utility'].fillna(
        df_combined['Utility_dr']
    ).fillna("Unknown Utility")

    df_combined = df_combined.drop(columns=['Utility_dr'])
    df_combined = df_combined.infer_objects().fillna(0)

    rename_dict = {
        c: f"{c}_{year}" for c in df_combined.columns
        if c not in ['Utility ID', 'Utility', 'State']
    }
    return df_combined.rename(columns=rename_dict)


def plot_dsm_comprehensive_dashboard(latest_yr, output_dir):
    base_year = latest_yr - 5
    print(f"Plotting: DSM potential ({latest_yr} vs {base_year})...")

    df_old = get_dsm_snapshot(base_year)
    df_new = get_dsm_snapshot(latest_yr)

    if df_old is None or df_new is None:
        return

    cols_to_keep = ['Utility ID', 'State'] + [
        c for c in df_old.columns if str(base_year) in c
    ]
    df_growth = pd.merge(
        df_new, df_old[cols_to_keep], on=['Utility ID', 'State'], how='left'
    ).infer_objects().fillna(0)

    agg_dict = {
        c: 'sum' for c in df_growth.columns
        if str(latest_yr) in c or str(base_year) in c
    }
    state_stats = df_growth.groupby('State').agg(agg_dict).reset_index()

    for sect in ['Res', 'Com', 'Ind', 'Trans']:
        state_stats[f'EE_Gr_{sect}'] = (
            state_stats[f'EE_{sect}_{latest_yr}'] -
            state_stats[f'EE_{sect}_{base_year}']
        )
        state_stats[f'DR_Gr_{sect}'] = (
            state_stats[f'DR_Pot_{sect}_{latest_yr}'] -
            state_stats[f'DR_Pot_{sect}_{base_year}']
        )

    state_stats['EE_State_Growth'] = (
        state_stats[f'EE_Total_{latest_yr}'] -
        state_stats[f'EE_Total_{base_year}']
    )
    state_stats['DR_State_Growth'] = (
        state_stats[f'DR_Pot_Total_{latest_yr}'] -
        state_stats[f'DR_Pot_Total_{base_year}']
    )

    def calc_pct(new, old):
        if old > 0:
            return int(round(((new - old) / old) * 100))
        return 100 if new > 0 else 0

    state_stats['EE_State_Pct'] = state_stats.apply(
        lambda r: calc_pct(
            r[f'EE_Total_{latest_yr}'], r[f'EE_Total_{base_year}']
        ), axis=1
    ).apply(lambda x: f"{x:+d}")

    state_stats['DR_State_Pct'] = state_stats.apply(
        lambda r: calc_pct(
            r[f'DR_Pot_Total_{latest_yr}'], r[f'DR_Pot_Total_{base_year}']
        ), axis=1
    ).apply(lambda x: f"{x:+d}")

    state_stats['DR_Util_Pct'] = (
        state_stats[f'DR_Act_Total_{latest_yr}'] /
        state_stats[f'DR_Pot_Total_{latest_yr}'] * 100
    ).fillna(0).round(0).astype(int)

    def get_top_util_pct(state, val_col, old_col):
        sub = df_growth[df_growth['State'] == state]
        if sub.empty:
            return "N/A", 0.0, "+0"
        top = sub.sort_values(val_col, ascending=False).iloc[0]
        pct_str = f"{calc_pct(top[val_col], top[old_col]):+d}"
        return str(top['Utility']), float(top[val_col]), pct_str

    ee_meta = state_stats['State'].apply(
        lambda x: get_top_util_pct(
            x, f'EE_Total_{latest_yr}', f'EE_Total_{base_year}'
        )
    )
    state_stats[['Top_EE_Name', 'Top_EE_Val', 'Top_EE_Str']] = pd.DataFrame(
        ee_meta.tolist(), index=state_stats.index
    )

    dr_meta = state_stats['State'].apply(
        lambda x: get_top_util_pct(
            x, f'DR_Pot_Total_{latest_yr}', f'DR_Pot_Total_{base_year}'
        )
    )
    state_stats[['Top_DR_Name', 'Top_DR_Val', 'Top_DR_Str']] = pd.DataFrame(
        dr_meta.tolist(), index=state_stats.index
    )

    top15_ee = state_stats.sort_values(
        'EE_State_Growth', ascending=False
    ).head(15)
    top15_dr = state_stats.sort_values(
        'DR_State_Growth', ascending=False
    ).head(15)

    fig = make_subplots(
        rows=2, cols=2,
        row_heights=[0.6, 0.4], vertical_spacing=0.1,
        horizontal_spacing=0.20,
        specs=[
            [{"type": "geo"}, {"type": "geo"}],
            [{"type": "xy"}, {"type": "xy"}]
        ],
        subplot_titles=(
            f"EE Avoided Peak, {latest_yr}<br><sup>Source: EIA 861</sup>",
            f"DR Avoided Peak, {latest_yr}<br><sup>Source: EIA 861</sup>",
            f"Highest EE Growth by Sector ({base_year}-{latest_yr})",
            f"Highest DR Growth by Sector ({base_year}-{latest_yr})"
        )
    )

    fig.update_xaxes(domain=[0.05, 0.45], row=2, col=1)
    fig.update_xaxes(domain=[0.55, 0.95], row=2, col=2)

    annotations = list(fig.layout.annotations)
    annotations[0].yshift = -15
    annotations[0].x = 0.245
    annotations[1].yshift = -15
    annotations[1].x = 0.755
    annotations[2].yshift = 15
    annotations[2].x = 0.25
    annotations[3].yshift = 15
    annotations[3].x = 0.75
    fig.layout.annotations = annotations

    b_size = 1.5
    hover_ee = (
        "<b>%{location}</b><br>"
        "State Total: %{marker.size:.1f} MW<br>"
        "5yr Growth: %{customdata[0]}%<br><br>"
        "Top Utility: %{customdata[1]}<br>"
        "Utility Potential: %{customdata[2]:.1f} MW<br>"
        "Utility Growth: %{customdata[3]}%<extra></extra>"
    )

    fig.add_trace(go.Scattergeo(
        locations=state_stats['State'], locationmode='USA-states',
        marker=dict(
            size=state_stats[f'EE_Total_{latest_yr}'], sizemode='area',
            sizeref=b_size, color='rgba(31, 119, 180, 0.7)',
            line=dict(width=1, color='white')
        ),
        customdata=state_stats[
            ['EE_State_Pct', 'Top_EE_Name', 'Top_EE_Val', 'Top_EE_Str']
        ],
        hovertemplate=hover_ee, name='EE Maps', showlegend=False
    ), row=1, col=1)

    hover_dr = (
        "<b>%{location} (Potential)</b><br>"
        "State Potential: %{marker.size:.1f} MW<br>"
        "5yr Growth: %{customdata[0]}%<br><br>"
        "Top Utility: %{customdata[1]}<br>"
        "Utility Potential: %{customdata[2]:.1f} MW<br>"
        "Utility Growth: %{customdata[3]}%<extra></extra>"
    )

    fig.add_trace(go.Scattergeo(
        locations=state_stats['State'], locationmode='USA-states',
        marker=dict(
            size=state_stats[f'DR_Pot_Total_{latest_yr}'], sizemode='area',
            sizeref=b_size, color='rgba(144, 238, 144, 0.4)',
            line=dict(width=0)
        ),
        customdata=state_stats[
            ['DR_State_Pct', 'Top_DR_Name', 'Top_DR_Val', 'Top_DR_Str']
        ],
        hovertemplate=hover_dr, name='DR Maps', showlegend=False
    ), row=1, col=2)

    fig.add_trace(go.Scattergeo(
        locations=state_stats['State'], locationmode='USA-states',
        marker=dict(
            size=state_stats[f'DR_Act_Total_{latest_yr}'], sizemode='area',
            sizeref=b_size, color='rgba(44, 160, 44, 0.9)',
            line=dict(width=1, color='white')
        ),
        customdata=state_stats[['DR_Util_Pct']],
        hovertemplate=(
            "<b>%{location} (Actual)</b><br>"
            "Actual MW Called: %{marker.size:.1f} MW<br>"
            "Utilization: %{customdata[0]}%<extra></extra>"
        ), showlegend=False
    ), row=1, col=2)

    colors = {
        'Res': '#1f77b4', 'Com': '#ff7f0e',
        'Ind': '#2ca02c', 'Trans': '#d62728'
    }
    sectors = [
        ('Res', 'Residential'), ('Com', 'Commercial'),
        ('Ind', 'Industrial'), ('Trans', 'Transportation')
    ]

    for suffix, label in sectors:
        fig.add_trace(go.Bar(
            x=top15_ee['State'], y=top15_ee[f'EE_Gr_{suffix}'],
            name=label, marker_color=colors[suffix], legendgroup=label,
            hovertemplate=(
                f"<b>%{{x}} - {label}</b><br>"
                "Growth: %{{y:+.1f}} MW<extra></extra>"
            )
        ), row=2, col=1)

        fig.add_trace(go.Bar(
            x=top15_dr['State'], y=top15_dr[f'DR_Gr_{suffix}'],
            name=label, marker_color=colors[suffix], legendgroup=label,
            showlegend=False,
            hovertemplate=(
                f"<b>%{{x}} - {label}</b><br>"
                "Growth: %{{y:+.1f}} MW<extra></extra>"
            )
        ), row=2, col=2)

    geo_config = dict(
        scope='usa', projection_type='albers usa', showland=True,
        landcolor='rgb(240, 240, 240)', subunitcolor='white'
    )

    fig.update_layout(
        dragmode="pan",
        showlegend=True,
        geo=dict(**geo_config, domain={'x': [0, 0.49]}),
        geo2=dict(**geo_config, domain={'x': [0.51, 1]}),
        barmode='relative',
        legend=dict(
            orientation="h", yanchor="top", y=-0.08, xanchor="center", x=0.5
        ),
        margin={"r": 0, "t": 35, "l": 0, "b": 70}, height=850
    )

    fig.update_yaxes(title_text="5-Year Growth (MW)", row=2, col=1)
    fig.update_yaxes(title_text="5-Year Growth (MW)", row=2, col=2)
    html_path = f"{output_dir}/dsm_potential.html"
    fig.write_html(
        html_path, default_width='100%', default_height='100%',
        config={'scrollZoom': True}
    )
    print(f"-> Success! DSM potential plots saved to {html_path}")


def plot_building_jobs_trend(bls_key, output_dir):
    """Buildings-related jobs trend."""
    print("Plotting: Buildings jobs (BLS)...")

    series_map = {
        'CEU2023822001': 'HVAC & Plumbing Contractors',
        'CEU2023821001': 'Electrical Contractors',
        'CEU2023610001': 'Residential Construction',
        'CEU2023620001': 'Commercial Construction',
        'CEU2023831001': 'Insulation & Weatherization',
        'CEU2023816001': 'Roofing Contractors',
        'CEU2023829001': 'Other Bldg. Equip. Contractors',
        'CEU6054130001': 'Architecture & Engineering',
        'CEU6054160001': 'Scientific/Tech Consulting',
        'CEU6056120001': 'Facilities Support Services',
        'CEU5553131201': 'Nonres. Property Managers',
        'CEU3133341501': 'HVAC & Refrigeration Mfg.',
        'CEU3133510001': 'Lighting Equip. Mfg.',
        'CEU3133590001': 'Other Elec. Equip. Mfg.'
    }

    group_map = {
        'HVAC & Plumbing Contractors': 'Equipment Installation',
        'Electrical Contractors': 'Equipment Installation',
        'Residential Construction': 'Construction',
        'Commercial Construction': 'Construction',
        'Insulation & Weatherization': 'Envelope Component Installation',
        'Roofing Contractors': 'Envelope Component Installation',
        'Other Bldg. Equip. Contractors': 'Equipment Installation',
        'Architecture & Engineering': 'Design and Construction Services',
        'Scientific/Tech Consulting': 'Design and Construction Services',
        'Facilities Support Services': 'Operations Services',
        'Nonres. Property Managers': 'Operations Services',
        'HVAC & Refrigeration Mfg.': 'Equipment Manufacturing',
        'Lighting Equip. Mfg.': 'Equipment Manufacturing',
        'Other Elec. Equip. Mfg.': 'Equipment Manufacturing'
    }

    colors = [
        '#1f77b4', '#ff7f0e', '#2ca02c', '#d62728',
        '#9467bd', '#8c564b', '#e377c2', '#7f7f7f',
        '#bcbd22', '#17becf', '#393b79', '#5254a3',
        '#6b6ecf', '#9c9ede'
    ]

    keys_list = list(group_map.keys())
    color_dict = {keys_list[i]: colors[i] for i in range(14)}

    headers = {'Content-type': 'application/json'}
    current_year = pd.Timestamp.now().year
    start_year = 2005

    records = []
    for chunk_start in range(start_year, current_year + 1, 10):
        chunk_end = min(chunk_start + 9, current_year)
        print(f" -> Fetching BLS data: {chunk_start} to {chunk_end}...")
        data = json.dumps({
            "seriesid": list(series_map.keys()),
            "startyear": str(chunk_start), "endyear": str(chunk_end),
            "registrationkey": bls_key
        })

        try:
            url = 'https://api.bls.gov/publicAPI/v2/timeseries/data/'
            req = requests.post(url, data=data, headers=headers, timeout=30)
            req.raise_for_status()
            json_data = req.json()
        except Exception as e:
            print(f"\n[WARNING] BLS API fetch failed ({chunk_start}): {e}")
            continue

        if json_data.get('status') != 'REQUEST_SUCCEEDED':
            err = json_data.get('message')
            print(f"\n[WARNING] BLS API Error ({chunk_start}): {err}")
            continue

        for series in json_data['Results']['series']:
            series_id = series['seriesID']
            series_name = series_map.get(series_id, series_id)

            for item in series['data']:
                period = item['period']
                if period == 'M13':
                    continue

                year = item['year']
                value = float(item['value'])
                month = period.replace('M', '').zfill(2)
                date_str = f"{year}-{month}-01"

                records.append({
                    'Date': date_str, 'Job Category': series_name,
                    'Legend Group': group_map.get(series_name, 'Other'),
                    'Employees (Thousands)': value
                })

    df = pd.DataFrame(records)
    if df.empty:
        print(" -> [WARNING] No data parsed from BLS.")
        return

    df['Date'] = pd.to_datetime(df['Date'])
    df = df.sort_values(['Job Category', 'Date'])

    df['Smoothed Jobs'] = df.groupby('Job Category')[
        'Employees (Thousands)'
    ].transform(lambda x: x.rolling(12, min_periods=1).mean())
    df = df[df['Date'] >= '2006-01-01'].copy()

    fig = go.Figure()
    fig.update_layout(hovermode="x unified")
    fig.update_xaxes(hoverformat="%b %Y")

    for grp in df['Legend Group'].unique():
        df_group = df[df['Legend Group'] == grp]

        for category in df_group['Job Category'].unique():
            df_cat = df_group[df_group['Job Category'] == category]
            fig.add_trace(go.Scatter(
                x=df_cat['Date'], y=df_cat['Smoothed Jobs'],
                mode='lines', name=category,
                line=dict(width=2, color=color_dict.get(category)),
                legendgroup=grp, legendgrouptitle_text=f"<b>{grp}</b>",
                hovertemplate="%{y:,.1f}k<extra></extra>"
            ))

    max_date = df['Date'].max()
    max_year = max_date.year
    max_month_name = max_date.strftime('%B')

    fig.update_layout(
        title=(
            f"Trends in Buildings-related Jobs (2006-{max_year})<br>"
            f"<sup>Source: BLS; Data through {max_month_name} {max_year}; "
            "12-Month Trailing Average</sup>"
        ),
        xaxis_title="Year", yaxis_title="Total Employees (Thousands)",
        template="plotly_white",
        legend=dict(
            orientation="v", yanchor="top", y=1.0, xanchor="left", x=1.02,
            groupclick="toggleitem"
        ),
        margin=dict(r=250, t=80, l=20, b=40),
        height=650
    )

    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    html_path = f"{output_dir}/building_jobs_trend.html"
    fig.write_html(html_path, default_width='100%', default_height='100%')
    print(f" -> Success! Buildings jobs HTML saved to {html_path}")


def plot_gdp_by_building_type(bea_key, output_dir):
    """Trends in buildings activity contribution to GDP (Real Dollars)."""
    print("Plotting: Buildings GDP contribution (BEA API)...")

    if not bea_key:
        print("\n[WARNING] BEA API key is missing. Skipping GDP plot.")
        return

    url = "https://apps.bea.gov/api/data/"
    params = {
        "UserID": bea_key, "method": "GetData", "datasetname": "GdpByIndustry",
        "TableID": "10", "Frequency": "A", "Year": "ALL",
        "Industry": "ALL", "ResultFormat": "JSON"
    }

    try:
        req = requests.get(url, params=params, timeout=30)
        req.raise_for_status()
        data = req.json()
    except Exception as e:
        print(f"\n[WARNING] BEA API fetch failed: {e}")
        return

    results_node = data.get('BEAAPI', {}).get('Results', {})
    if isinstance(results_node, dict) and 'Error' in results_node:
        err_msg = results_node['Error'].get(
            'ErrorDetail', results_node['Error']
        )
        print(f"\n[WARNING] BEA API Error: {err_msg}")
        return

    try:
        if isinstance(results_node, list):
            results = results_node[0]['Data']
        else:
            results = results_node['Data']
        df = pd.DataFrame(results)
    except (KeyError, IndexError, TypeError) as e:
        print(f"\n[WARNING] Unexpected BEA API response structure: {e}")
        return

    if df.empty:
        print("\n[WARNING] No data returned from BEA API.")
        return

    df['DataValue'] = pd.to_numeric(df['DataValue'], errors='coerce')
    df['Year'] = pd.to_numeric(df['Year'], errors='coerce')

    max_gdp_year = int(df['Year'].max())
    min_gdp_year = max_gdp_year - 20

    print(
        f" -> Found GDP data through {max_gdp_year}. "
        f"Plotting {min_gdp_year}-{max_gdp_year}."
    )
    df = df[(df['Year'] >= min_gdp_year) & (df['Year'] <= max_gdp_year)]

    mapping = {
        '53': 'Residential (Real Estate & Housing)',
        '44RT': 'Commercial (Offices, Retail, Services)',
        '51': 'Commercial (Offices, Retail, Services)',
        '52': 'Commercial (Offices, Retail, Services)',
        '54': 'Commercial (Offices, Retail, Services)',
        '55': 'Commercial (Offices, Retail, Services)',
        '56': 'Commercial (Offices, Retail, Services)',
        '61': 'Commercial (Offices, Retail, Services)',
        '62': 'Commercial (Offices, Retail, Services)',
        '71': 'Commercial (Offices, Retail, Services)',
        '72': 'Commercial (Offices, Retail, Services)',
        '81': 'Commercial (Offices, Retail, Services)',
        'G': 'Commercial (Offices, Retail, Services)',
        '11': 'Industrial / Other', '21': 'Industrial / Other',
        '22': 'Industrial / Other', '23': 'Industrial / Other',
        '31G': 'Industrial / Other', '42': 'Industrial / Other',
        '48TW': 'Industrial / Other'
    }

    df_filtered = df[df['Industry'].isin(mapping.keys())].copy()
    df_filtered['Category'] = df_filtered['Industry'].map(mapping)

    df_agg = df_filtered.groupby(
        ['Year', 'Category']
    )['DataValue'].sum().reset_index()
    total_gdp = df_agg.groupby('Year')['DataValue'].sum().reset_index()
    total_gdp.rename(columns={'DataValue': 'Total_GDP'}, inplace=True)
    df_agg = pd.merge(df_agg, total_gdp, on='Year')
    df_agg['Share'] = (df_agg['DataValue'] / df_agg['Total_GDP']) * 100

    cat_order = [
        'Industrial / Other',
        'Residential (Real Estate & Housing)',
        'Commercial (Offices, Retail, Services)'
    ]

    fig = go.Figure()
    colors = {
        'Commercial (Offices, Retail, Services)': '#1f77b4',
        'Residential (Real Estate & Housing)': '#ff7f0e',
        'Industrial / Other': '#7f7f7f'
    }

    for cat in cat_order:
        df_plot = df_agg[df_agg['Category'] == cat].sort_values('Year')
        fig.add_trace(go.Scatter(
            x=df_plot['Year'], y=df_plot['DataValue'], name=cat, mode='lines',
            line=dict(width=0.5, color=colors[cat]), stackgroup='one',
            fillcolor=colors[cat], customdata=df_plot[['Share']],
            hovertemplate=(
                "Real Value Added: $%{y:,.0f} Billion<br>"
                "Share of GDP: %{customdata[0]:.1f}%<extra></extra>"
            )
        ))

    fig.update_layout(
        title=(
            "Real GDP Contributions of Activities in Buildings, "
            f"{min_gdp_year}-{max_gdp_year}<br>"
            "<sup>Source: BEA (Inflation-Adjusted Chained Dollars)</sup>"
        ),
        xaxis_title="Year", yaxis_title="Real GDP Contribution ($ Billions)",
        template="plotly_white", hovermode="x unified",
        legend=dict(
            orientation="h", yanchor="top", y=-0.15, xanchor="center", x=0.5
        ),
        margin=dict(r=40, t=80, l=40, b=80), height=700
    )

    fig.update_xaxes(dtick=2)
    html_path = f"{output_dir}/gdp_contributions.html"
    fig.write_html(html_path, default_width='100%', default_height='100%')
    print(f" -> Success! GDP wedge HTML saved to {html_path}")


def plot_ferc_load_growth_forecasts(output_dir):
    """Maps FERC 714 load growth, separating RTOs from Retail Utilities."""
    print("Plotting: FERC load growth forecasts...")

    geojson_url = (
        'https://raw.githubusercontent.com/plotly/datasets/master/'
        'geojson-counties-fips.json'
    )
    try:
        req = Request(geojson_url, headers={'User-Agent': 'Mozilla/5.0'})
        with urlopen(req) as response:
            counties = json.load(response)

        county_fips_list = [feature['id'] for feature in counties['features']]
        df_all_counties = pd.DataFrame({'FIPS': county_fips_list})
        df_all_counties['state_fips'] = df_all_counties['FIPS'].str[:2]

        county_gdf = gpd.read_file(geojson_url)
        county_gdf['lon'] = county_gdf.to_crs(
            epsg=3857).centroid.to_crs(epsg=4326).x
        county_gdf['lat'] = county_gdf.to_crs(
            epsg=3857).centroid.to_crs(epsg=4326).y
        county_coords = county_gdf[['id', 'lon', 'lat']].rename(
            columns={'id': 'FIPS'}
        )
    except Exception as e:
        print(f"\n[ERROR] Failed to download county GeoJSON: {e}")
        return

    base_url = "https://s3.us-west-2.amazonaws.com/pudl.catalyst.coop/eel-hole"
    try:
        print(" -> Fetching PUDL Datasets...")
        df_crosswalk = pd.read_parquet(
            f"{base_url}/core_ferc714__respondent_id.parquet"
        )
        df_ferc_all = pd.read_parquet(
            f"{base_url}/core_ferc714__yearly_planning_area_demand_"
            "forecast.parquet"
        )
        df_terr_all = pd.read_parquet(
            f"{base_url}/core_eia861__yearly_service_territory.parquet"
        )
        terr_date_col = (
            'report_year' if 'report_year' in df_terr_all.columns
            else 'report_date'
        )
        df_terr = df_terr_all[
            df_terr_all[terr_date_col] == df_terr_all[terr_date_col].max()
        ].copy()
    except Exception as e:
        print(f"\n[ERROR] PUDL fetch failed: {e}")
        return

    date_col = (
        'report_year' if 'report_year' in df_ferc_all.columns
        else 'report_date'
    )
    df_ferc_all['report_year_clean'] = (
        pd.to_datetime(df_ferc_all[date_col]).dt.year if
        date_col == 'report_date' else df_ferc_all[date_col]
    )

    latest_yr = df_ferc_all['report_year_clean'].max()
    df_latest = df_ferc_all[
        df_ferc_all['report_year_clean'] == latest_yr
    ].copy()
    df_latest['years_out'] = (
        df_latest['forecast_year'] - df_latest['report_year_clean']
    )

    df_latest['peak_mw'] = df_latest[
        ['summer_peak_demand_forecast_mw', 'winter_peak_demand_forecast_mw']
    ].max(axis=1)

    df_latest = df_latest.dropna(subset=['peak_mw'])

    df_latest = df_latest.sort_values(['respondent_id_ferc714', 'years_out'])
    df_baseline = df_latest.groupby(
        'respondent_id_ferc714'
    ).first().reset_index()
    df_baseline = df_baseline[['respondent_id_ferc714', 'peak_mw']].rename(
        columns={'peak_mw': 'baseline_mw'}
    )

    df_latest['dist_5'] = (df_latest['years_out'] - 5).abs()
    df_5yr = df_latest.sort_values(
        ['respondent_id_ferc714', 'dist_5']
    ).groupby('respondent_id_ferc714').first().reset_index()
    df_5yr = df_5yr[['respondent_id_ferc714', 'peak_mw']].rename(
        columns={'peak_mw': 'peak_5yr'}
    )

    df_latest['dist_10'] = (df_latest['years_out'] - 10).abs()
    df_10yr = df_latest.sort_values(
        ['respondent_id_ferc714', 'dist_10']
    ).groupby('respondent_id_ferc714').first().reset_index()
    df_10yr = df_10yr[['respondent_id_ferc714', 'peak_mw']].rename(
        columns={'peak_mw': 'peak_10yr'}
    )

    df_growth = df_baseline.merge(
        df_5yr, on='respondent_id_ferc714', how='left'
    )
    df_growth = df_growth.merge(
        df_10yr, on='respondent_id_ferc714', how='left'
    )

    df_growth['delta_5yr'] = (
        df_growth['peak_5yr'] - df_growth['baseline_mw']
    ).fillna(0)
    df_growth['pct_5yr'] = np.where(
        df_growth['baseline_mw'] > 0,
        (df_growth['delta_5yr'] / df_growth['baseline_mw']) * 100, 0
    )

    df_growth['delta_10yr'] = (
        df_growth['peak_10yr'] - df_growth['baseline_mw']
    ).fillna(0)
    df_growth['pct_10yr'] = np.where(
        df_growth['baseline_mw'] > 0,
        (df_growth['delta_10yr'] / df_growth['baseline_mw']) * 100, 0
    )

    df_growth['bubble_5yr'] = df_growth['delta_5yr'].fillna(0).clip(lower=10)
    df_growth['bubble_10yr'] = df_growth['delta_10yr'].fillna(0).clip(lower=10)

    df_terr['FIPS'] = df_terr['state_id_fips'].astype(str).str.zfill(2) + \
        df_terr['county_id_fips'].astype(str).str.zfill(3).str[-3:]

    eia_col = (
        'eia_code' if 'eia_code' in df_crosswalk.columns
        else 'utility_id_eia'
    )
    df_cw_exp = df_crosswalk.dropna(subset=[eia_col]).copy()
    df_cw_exp[eia_col] = df_cw_exp[eia_col].astype(str).str.replace(
        r'\[|\]', '', regex=True
    )
    df_cw_exp = df_cw_exp.assign(
        **{eia_col: df_cw_exp[eia_col].str.split(',')}
    ).explode(eia_col)

    df_cw_exp['join_id'] = pd.to_numeric(
        df_cw_exp[eia_col], errors='coerce'
    ).fillna(-1).astype(int)
    df_terr['join_id'] = pd.to_numeric(
        df_terr['utility_id_eia'], errors='coerce'
    ).fillna(-2).astype(int)

    df_retail = pd.merge(
        df_cw_exp[['respondent_id_ferc714', 'join_id']],
        df_terr[['join_id', 'FIPS']], on='join_id'
    )[['respondent_id_ferc714', 'FIPS']]

    rto_states = {
        'PJM': ['42', '34', '24', '10', '39', '51', '54', '11', '17', '18',
                '26', '21', '37', '47'],
        'Midcontinent|MISO': ['27', '55', '19', '17', '18', '26', '29', '05',
                              '22', '28', '38', '46', '30', '48'],
        'Southwest Power|SPP': ['20', '40', '31', '38', '46', '48', '35', '29',
                                '05', '22', '30', '56'],
        'California Independent|CAISO': ['06'],
        'New York Independent|NYISO': ['36'],
        'ISO New England|ISONE': ['09', '23', '25', '33', '44', '50'],
        'Electric Reliability Council of Texas|ERCOT': ['48']
    }

    rto_rows = []
    rto_ids = []
    for name_key, state_list in rto_states.items():
        match = df_crosswalk[
            df_crosswalk['respondent_name_ferc714'].str.contains(
                name_key, case=False, regex=True, na=False
            )
        ]
        if not match.empty:
            for rto_id in match['respondent_id_ferc714'].unique():
                rto_ids.append(rto_id)
                fips_list = df_all_counties[
                    df_all_counties['state_fips'].isin(state_list)
                ]['FIPS'].tolist()
                for fips in fips_list:
                    rto_rows.append({
                        'respondent_id_ferc714': rto_id, 'FIPS': fips
                    })

    df_master = pd.concat([df_retail, pd.DataFrame(rto_rows)]).drop_duplicates()

    df_spatial_coords = pd.merge(df_master, county_coords, on='FIPS')
    ba_centroids = df_spatial_coords.groupby(
        'respondent_id_ferc714'
    )[['lon', 'lat']].mean().reset_index()

    df_map = pd.merge(df_growth, ba_centroids, on='respondent_id_ferc714')
    df_map = pd.merge(
        df_map,
        df_crosswalk[['respondent_id_ferc714', 'respondent_name_ferc714']],
        on='respondent_id_ferc714'
    )

    df_map['Entity_Type'] = np.where(
        df_map['respondent_id_ferc714'].isin(rto_ids),
        'Wholesale RTO/ISO', 'Retail/Vertically Integrated'
    )

    df_map = df_map.dropna(subset=['lon', 'lat', 'bubble_5yr', 'bubble_10yr'])
    df_map = df_map[df_map['baseline_mw'] > 0].copy()

    max_delta = max(df_map['bubble_10yr'].max(), df_map['bubble_5yr'].max())
    sizeref = 2.0 * max_delta / (45 ** 2) if max_delta > 0 else 1

    fig = make_subplots(
        rows=1, cols=2,
        specs=[[{'type': 'scattergeo'}, {'type': 'scattergeo'}]],
        subplot_titles=(
            f"5-Year Projection, {latest_yr}<br>"
            "<sup>Source: FERC Form 714 via PUDL</sup>",
            f"10-Year Projection, {latest_yr}<br>"
            "<sup>Source: FERC Form 714 via PUDL</sup>"
        ),
        horizontal_spacing=0
    )

    annotations = list(fig.layout.annotations)
    for a in annotations:
        a.yshift = -25
    fig.layout.annotations = annotations

    cmax_val = df_map['pct_10yr'].quantile(0.95)

    for ent_type in ['Retail/Vertically Integrated', 'Wholesale RTO/ISO']:
        df_sub = df_map[df_map['Entity_Type'] == ent_type]
        marker_symbol = (
            'diamond' if ent_type == 'Wholesale RTO/ISO' else 'circle'
        )
        marker_line_width = 0.5
        marker_line_color = 'black'

        for col_num, (size_col, delta_col, pct_col) in enumerate([
            ('bubble_5yr', 'delta_5yr', 'pct_5yr'),
            ('bubble_10yr', 'delta_10yr', 'pct_10yr')
        ], 1):
            show_colorbar = (
                col_num == 2 and ent_type == 'Retail/Vertically Integrated'
            )

            fig.add_trace(
                go.Scattergeo(
                    lon=df_sub['lon'], lat=df_sub['lat'],
                    text=df_sub['respondent_name_ferc714'],
                    marker=dict(
                        symbol=marker_symbol, size=df_sub[size_col],
                        sizemode='area', sizeref=sizeref, sizemin=4,
                        color=df_sub[pct_col], colorscale='YlOrRd', cmin=0,
                        cmax=cmax_val, showscale=show_colorbar,
                        colorbar=dict(
                            title="Growth (%)", x=1.02, len=0.6, y=0.5
                        ) if show_colorbar else None,
                        line_color=marker_line_color,
                        line_width=marker_line_width, opacity=0.85
                    ),
                    customdata=df_sub[[
                        'respondent_name_ferc714', 'Entity_Type',
                        'baseline_mw', delta_col, pct_col
                    ]],
                    hovertemplate=(
                        "<b>%{customdata[0]}</b> (%{customdata[1]})<br>"
                        "Current Baseline: %{customdata[2]:,.0f} MW<br>"
                        "Projected Growth: <b>+%{customdata[3]:,.0f} MW</b><br>"
                        "Growth Rate: <b>%{customdata[4]:.1f}%</b><extra></extra>"
                    ),
                    name=ent_type, legendgroup=ent_type,
                    showlegend=(col_num == 1)
                ), row=1, col=col_num
            )

    fig.update_layout(
        dragmode="pan",
        title_x=0.5, height=700,
        geo=dict(
            scope='usa', projection_type='albers usa', showland=True,
            landcolor="rgb(235, 240, 240)"
        ),
        geo2=dict(
            scope='usa', projection_type='albers usa', showland=True,
            landcolor="rgb(235, 240, 240)"
        ),
        margin={"r": 0, "t": 40, "l": 0, "b": 40},
        legend=dict(
            orientation="h", yanchor="top", y=0.04, xanchor="center", x=0.5,
            itemsizing="constant"
        )
    )

    html_path = f"{output_dir}/load_forecasts.html"
    fig.write_html(
        html_path, default_width='100%', default_height='100%',
        config={'scrollZoom': True}
    )
    print(f" -> Success! Load forecasts HTML ({len(df_map)} Planning Areas).")


def plot_insurance_costs(output_dir):
    """Fetches 2023 ACS 5-Year estimates and calculates median costs."""
    print("Plotting: Homeowner insurance costs (ACS 2023)...")

    target_year = pd.Timestamp.now().year
    success_acs = False

    while target_year >= 2021:
        bucket_suffixes = [
            ('003', '016'), ('004', '017'), ('005', '018'), ('006', '019'),
            ('007', '020'), ('008', '021'), ('009', '022'), ('010', '023'),
            ('011', '024'), ('012', '025'), ('013', '026'), ('014', '027')
        ]

        variables = ['NAME', 'B25141_001E']
        for m_suffix, nm_suffix in bucket_suffixes:
            variables.extend([f'B25141_{m_suffix}E', f'B25141_{nm_suffix}E'])

        api_url = (
            f"https://api.census.gov/data/{target_year}/acs/acs5?"
            f"get={','.join(variables)}&for=county:*"
        )

        try:
            print(f" -> Checking Census ACS API for {target_year}...")
            res = requests.get(api_url, timeout=15)
            if res.status_code == 200:
                data = res.json()
                df_acs = pd.DataFrame(data[1:], columns=data[0])
                print(f" -> Success! Found ACS data for {target_year}.")
                success_acs = True
                break
        except Exception:
            pass
        target_year -= 1

    if not success_acs:
        print("\n[ERROR] Could not find any valid ACS data years.")
        return

    boundary_year = target_year
    counties = None
    while boundary_year >= 2022:
        census_shp_url = (
            f"https://www2.census.gov/geo/tiger/GENZ{boundary_year}/"
            f"shp/cb_{boundary_year}_us_county_20m.zip"
        )
        try:
            print(f" -> Attempting to fetch boundaries for {boundary_year}...")
            gdf = gpd.read_file(census_shp_url)
            counties = json.loads(gdf.to_json())
            print(f" -> Success! Using {boundary_year} boundary files.")
            break
        except Exception:
            boundary_year -= 1

    if counties is None:
        print("\n[ERROR] Failed to download valid Census boundaries.")
        return

    val_cols = [col for col in df_acs.columns if col.startswith('B25141')]
    df_acs[val_cols] = df_acs[val_cols].apply(
        pd.to_numeric, errors='coerce'
    ).fillna(0)

    for i, (m, nm) in enumerate(bucket_suffixes, 1):
        df_acs[f'bucket_{i}'] = df_acs[f'B25141_{m}E'] + df_acs[f'B25141_{nm}E']

    bounds = [
        (0, 100), (100, 150), (250, 250), (500, 250),
        (750, 250), (1000, 500), (1500, 500), (2000, 500),
        (2500, 500), (3000, 500), (3500, 500), (4000, 0)
    ]

    def calc_median(row):
        total_hh = sum(row[f'bucket_{i}'] for i in range(1, 13))
        if total_hh == 0:
            return 0

        target_hh = total_hh / 2.0
        cumulative = 0

        for i in range(1, 13):
            freq = row[f'bucket_{i}']
            if cumulative + freq >= target_hh:
                lower_bound, width = bounds[i-1]
                if i == 12:
                    return 4000
                if freq == 0:
                    return lower_bound
                fraction = (target_hh - cumulative) / freq
                return lower_bound + (fraction * width)
            cumulative += freq
        return 0

    print(" -> Calculating interpolated medians...")
    df_acs['interpolated_median'] = df_acs.apply(calc_median, axis=1)

    df_acs['state_clean'] = df_acs['state'].astype(str).str.zfill(2)
    df_acs['county_clean'] = df_acs['county'].astype(str).str.zfill(3)
    df_acs['FIPS'] = df_acs['state_clean'] + df_acs['county_clean']

    df_map = df_acs[df_acs['B25141_001E'] > 0].copy()

    print(" -> Building HTML Choropleth Map...")
    fig = px.choropleth(
        df_map,
        geojson=counties, locations='FIPS', featureidkey="properties.GEOID",
        color='interpolated_median', color_continuous_scale="Plasma",
        range_color=(df_map['interpolated_median'].quantile(0.05),
                     df_map['interpolated_median'].quantile(0.95)),
        scope="usa", hover_name='NAME',
        hover_data={
            'FIPS': False, 'interpolated_median': ':$,.0f',
            'B25141_001E': ':,'
        },
        labels={
            'interpolated_median': 'Median Cost ($)',
            'B25141_001E': 'Total Homeowners'
        }
    )

    fig.update_layout(
        dragmode="pan",
        title_text=(
            f"Homeowners Insurance Costs, {target_year}<br>"
            "<sup>Source: Census ACS; Median, includes fire, hazard, "
            "and flood</sup>"
        ),
        title_x=0.5,
        margin={"r": 0, "t": 60, "l": 0, "b": 0}, height=700,
        coloraxis_colorbar=dict(len=0.6, y=0.5)
    )

    html_path = f"{output_dir}/insurance_costs.html"
    fig.write_html(
        html_path, default_width='100%', default_height='100%',
        config={'scrollZoom': True}
    )
    print(f" -> Success! Insurance costs HTML saved to {html_path}")


def plot_price_expend_benchmarks(output_dir):
    """Fetches historical and modern EIA data and plots 2000-benchmarks."""
    print("Plotting: Trends in energy prices and expenditures...")

    def fetch_excel(url, sheet_name=0, header=None, skiprows=0):
        headers = {"User-Agent": "Mozilla/5.0"}
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()
        return pd.read_excel(
            io.BytesIO(response.content),
            sheet_name=sheet_name,
            header=header,
            skiprows=skiprows,
        )

    try:
        print(" -> Fetching Historical Electricity (1990-2020)...")
        base_elec = "https://www.eia.gov/electricity/data/state"

        df_rev = fetch_excel(
            f"{base_elec}/revenue_annual.xlsx", header=0, skiprows=1
        )
        df_sales = fetch_excel(
            f"{base_elec}/sales_annual.xlsx", header=0, skiprows=1
        )
        df_cust = fetch_excel(
            f"{base_elec}/customers_annual.xlsx", header=0, skiprows=1
        )

        def clean_elec_hist(df):
            cols = [str(c).lower() for c in df.columns]
            yr_col = df.columns[next(i for i, c in enumerate(cols)
                                     if "year" in c)]
            st_col = df.columns[next(i for i, c in enumerate(cols)
                                     if "state" in c)]
            sec_col = df.columns[
                next(i for i, c in enumerate(cols)
                     if "sector" in c or "industry" in c)
            ]
            res_col = df.columns[next(i for i, c in enumerate(cols)
                                      if "residential" in c)]
            com_col = df.columns[next(i for i, c in enumerate(cols)
                                      if "commercial" in c)]

            df = df.rename(columns={
                yr_col: "Year", st_col: "State", sec_col: "Sector",
                res_col: "Residential", com_col: "Commercial",
            })

            sector_clean = df["Sector"].astype(str).str.lower().str.replace(
                r"[^a-z]", "", regex=True
            )
            df = df[sector_clean.str.contains("totalelectricindustry")]
            df = df[df["State"] != "US"]

            for col in ["Residential", "Commercial"]:
                df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)

            return df.groupby(
                "Year"
            )[["Residential", "Commercial"]].sum().reset_index()

        df_elec_old = clean_elec_hist(df_rev).merge(
            clean_elec_hist(df_sales), on="Year", suffixes=("_rev", "_sales")
        ).merge(clean_elec_hist(df_cust), on="Year")

        df_elec_old.rename(
            columns={
                "Residential": "Residential_cust",
                "Commercial": "Commercial_cust"
            }, inplace=True
        )

        print(" -> Fetching Modern EIA-861M Electricity (2021-Present)...")
        recent_dfs = []
        base_861 = "https://www.eia.gov/electricity/data/eia861m"

        for year in range(2021, 2027):
            urls_to_try = [
                f"{base_861}/xls/sales_ult_cust_{year}.xlsx",
                f"{base_861}/archive/xls/sales_ult_cust_{year}.xlsx",
            ]

            df = None
            for url in urls_to_try:
                try:
                    df = fetch_excel(url, header=0, skiprows=2)
                    break
                except Exception:
                    continue

            if df is not None:
                try:
                    df_agg = df.iloc[:, [0, 1, 4, 7, 8, 9, 10, 11, 12]].copy()
                    df_agg.columns = [
                        "Year", "Month", "State", "Res_Rev", "Res_Sales",
                        "Res_Cust", "Com_Rev", "Com_Sales", "Com_Cust"
                    ]

                    df_agg = df_agg.dropna(subset=["State"])
                    df_agg = df_agg[
                        ~df_agg["State"].astype(str).str.contains(
                            "US", case=False
                        )
                    ]

                    agg_cols = [
                        "Res_Rev", "Res_Sales", "Res_Cust", "Com_Rev",
                        "Com_Sales", "Com_Cust"
                    ]
                    for col in agg_cols:
                        df_agg[col] = pd.to_numeric(
                            df_agg[col], errors="coerce"
                        ).fillna(0)

                    df_month = df_agg.groupby("Month")[agg_cols].sum().\
                        reset_index()

                    if len(df_month) == 12:
                        annual = {
                            "Year": year,
                            "Residential_rev": df_month["Res_Rev"].sum(),
                            "Residential_sales": df_month["Res_Sales"].sum(),
                            "Residential_cust": df_month["Res_Cust"].mean(),
                            "Commercial_rev": df_month["Com_Rev"].sum(),
                            "Commercial_sales": df_month["Com_Sales"].sum(),
                            "Commercial_cust": df_month["Com_Cust"].mean(),
                        }
                        if annual["Residential_sales"] > 0:
                            recent_dfs.append(pd.DataFrame([annual]))
                except Exception as e:
                    print(f"    [Diagnostic] Could not parse {year}: {e}")

        if recent_dfs:
            df_elec_new = pd.concat(recent_dfs, ignore_index=True)
            df_elec_raw = pd.concat(
                [df_elec_old, df_elec_new], ignore_index=True
            )
        else:
            df_elec_raw = df_elec_old

        print(" -> Fetching EIA Natural Gas files...")
        base_ng = "https://www.eia.gov/dnav/ng/xls"
        ng_urls = {
            "pri_res": f"{base_ng}/NG_PRI_SUM_A_EPG0_PRS_DMCF_A.xls",
            "pri_com": f"{base_ng}/NG_PRI_SUM_A_EPG0_PCS_DMCF_A.xls",
            "vol_res": f"{base_ng}/NG_CONS_SUM_A_EPG0_VRS_MMCF_A.xls",
            "vol_com": f"{base_ng}/NG_CONS_SUM_A_EPG0_VCS_MMCF_A.xls",
            "cust_res": f"{base_ng}/NG_CONS_NUM_A_EPG0_VN3_COUNT_A.xls",
            "cust_com": f"{base_ng}/NG_CONS_NUM_A_EPG0_VN4_COUNT_A.xls",
        }

        def clean_ng(df, name):
            header_idx = None
            date_col_name = None

            for idx, row in df.head(15).iterrows():
                for cell in row:
                    val = str(cell).strip().lower()
                    if val in ["date", "year", "month"]:
                        header_idx = idx
                        date_col_name = cell
                        break
                if header_idx is not None:
                    break

            if header_idx is None:
                raise ValueError(f"Missing header row in {name}")

            df.columns = df.iloc[header_idx]
            df = df.iloc[header_idx + 1:].reset_index(drop=True)

            us_col = next(
                (col for col in df.columns if isinstance(col, str)
                 and ("U.S." in col or "United States" in col)), None
            )

            df = df[[date_col_name, us_col]].copy()
            df.rename(
                columns={date_col_name: "Date", us_col: name}, inplace=True
            )
            df["Year"] = pd.to_datetime(df["Date"], errors="coerce").dt.year
            df = df.dropna(subset=["Year"])
            df["Year"] = df["Year"].astype(int)
            df[name] = pd.to_numeric(df[name], errors="coerce")
            return df[["Year", name]]

        ng_dfs = []
        for key, url in ng_urls.items():
            ng_dfs.append(clean_ng(
                fetch_excel(url, sheet_name='Data 1', header=None), key
            ))

        df_ng_raw = ng_dfs[0]
        for d in ng_dfs[1:]:
            df_ng_raw = df_ng_raw.merge(d, on="Year", how="outer")

        print(" -> Fetching FRED CPI data...")
        try:
            fred_headers = {
                "User-Agent": "Mozilla/5.0",
                "Accept": "text/html,application/xhtml+xml,application/xml"
            }
            cpi_url = "https://fred.stlouisfed.org/graph/fredgraph.csv?id=CPIAUCNS"
            cpi_resp = requests.get(cpi_url, headers=fred_headers, timeout=10)
            cpi_resp.raise_for_status()

            df_cpi = pd.read_csv(io.StringIO(cpi_resp.text))
            date_col = next(c for c in df_cpi.columns if "date" in c.lower())
            val_col = next(c for c in df_cpi.columns if "cpi" in c.lower())

            df_cpi["Year"] = pd.to_datetime(df_cpi[date_col]).dt.year
            df_cpi["CPI"] = pd.to_numeric(df_cpi[val_col], errors="coerce")
            cpi_agg = df_cpi.groupby("Year")["CPI"].mean().reset_index()
        except Exception:
            cpi_dict = {
                2000: 172.2, 2001: 177.1, 2002: 179.9, 2003: 184.0,
                2004: 188.9, 2005: 195.3, 2006: 201.6, 2007: 207.3,
                2008: 215.3, 2009: 214.5, 2010: 218.1, 2011: 224.9,
                2012: 229.6, 2013: 233.0, 2014: 236.7, 2015: 237.0,
                2016: 240.0, 2017: 245.1, 2018: 251.1, 2019: 255.7,
                2020: 258.8, 2021: 271.0, 2022: 292.6, 2023: 304.7,
                2024: 314.0, 2025: 320.0, 2026: 325.0,
            }
            cpi_agg = pd.DataFrame(
                list(cpi_dict.items()), columns=["Year", "CPI"]
            )

        df_master = df_elec_raw.merge(df_ng_raw, on="Year", how="outer")
        df_master = df_master.merge(cpi_agg, on="Year", how="outer")

        current_year = pd.Timestamp.now().year
        df_master = df_master[
            (df_master["Year"] >= 2000) & (df_master["Year"] <= current_year)
        ].sort_values("Year")

        lagging_metrics = [
            "Residential_cust", "Commercial_cust", "cust_res", "cust_com"
        ]
        for col in lagging_metrics:
            if col in df_master.columns:
                df_master[col] = df_master[col].ffill(limit=2)

        df_master["elec_res_price"] = (
            df_master["Residential_rev"] / df_master["Residential_sales"]
        )
        df_master["elec_com_price"] = (
            df_master["Commercial_rev"] / df_master["Commercial_sales"]
        )
        df_master["elec_res_exp"] = (
            (df_master["Residential_rev"] * 1000) / df_master["Residential_cust"]
        )
        df_master["elec_com_exp"] = (
            (df_master["Commercial_rev"] * 1000) / df_master["Commercial_cust"]
        )

        df_master["ng_res_price"] = df_master["pri_res"]
        df_master["ng_com_price"] = df_master["pri_com"]
        df_master["ng_res_exp"] = (
            (df_master["vol_res"] * 1000 * df_master["pri_res"]) /
            df_master["cust_res"]
        )
        df_master["ng_com_exp"] = (
            (df_master["vol_com"] * 1000 * df_master["pri_com"]) /
            df_master["cust_com"]
        )

        target_cols = [
            "elec_res_price", "elec_com_price", "elec_res_exp", "elec_com_exp",
            "ng_res_price", "ng_com_price", "ng_res_exp", "ng_com_exp"
        ]
        df_master = df_master.dropna(subset=target_cols)

        latest_yr = int(df_master["Year"].max())
        cpi_latest = df_master.loc[
            df_master["Year"] == latest_yr, "CPI"
        ].values[0]

        for col in target_cols:
            df_master[f"{col}_real"] = (
                df_master[col] * (cpi_latest / df_master["CPI"])
            )

        base_year_df = df_master[df_master["Year"] == 2000]
        for col in target_cols:
            base_val = base_year_df[f"{col}_real"].values[0]
            df_master[f"{col}_idx"] = (df_master[f"{col}_real"] / base_val) * 100

        print(f" -> Building HTML Dashboard (Extended to {latest_yr})...")
        fig = make_subplots(
            rows=1, cols=2,
            subplot_titles=(
                f"Trend in Energy Prices<br>"
                f"<sup>Source: EIA; Real {latest_yr} dollars</sup>",
                f"Trend in Energy Expenditures per Customer<br>"
                f"<sup>Source: EIA; Real {latest_yr} dollars</sup>"
            ),
            shared_yaxes=True,
            horizontal_spacing=0.08,
        )

        metrics = {
            "elec_res": {"name": "Electricity - Residential",
                         "c": "#0366d6", "d": "solid"},
            "elec_com": {"name": "Electricity - Commercial",
                         "c": "#0366d6", "d": "dash"},
            "ng_res": {"name": "Natural Gas - Residential",
                       "c": "#d73a49", "d": "solid"},
            "ng_com": {"name": "Natural Gas - Commercial",
                       "c": "#d73a49", "d": "dash"},
        }

        for key, style in metrics.items():
            fig.add_trace(go.Scatter(
                x=df_master["Year"], y=df_master[f"{key}_price_idx"],
                name=style["name"], legendgroup=key, mode="lines+markers",
                line=dict(color=style["c"], dash=style["d"], width=2.5),
                marker=dict(size=6),
                hovertemplate=(
                    f"<b>{style['name']}</b><br>"
                    "Year: %{x}<br>Index: %{y:.1f}<extra></extra>"
                ),
            ), row=1, col=1)

            fig.add_trace(go.Scatter(
                x=df_master["Year"], y=df_master[f"{key}_exp_idx"],
                name=style["name"], legendgroup=key, showlegend=False,
                mode="lines+markers",
                line=dict(color=style["c"], dash=style["d"], width=2.5),
                marker=dict(size=6),
                hovertemplate=(
                    f"<b>{style['name']}</b><br>"
                    "Year: %{x}<br>Index: %{y:.1f}<extra></extra>"
                ),
            ), row=1, col=2)

        fig.add_hline(
            y=100, line_dash="dot", line_color="black", row="all", col="all",
            annotation_text="Year 2000 Baseline",
            annotation_position="bottom right",
        )

        fig.update_layout(
            title_x=0.5, height=600, margin=dict(t=80, b=80, l=40, r=40),
            legend=dict(
                orientation="h", yanchor="top", y=-0.15, xanchor="center", x=0.5
            ),
            plot_bgcolor="rgba(0,0,0,0)",
        )

        fig.update_xaxes(
            showgrid=True, gridcolor="lightgray", title_text="Year"
        )
        fig.update_yaxes(
            showgrid=True, gridcolor="lightgray",
            title_text="Index (2000 = 100)", col=1
        )
        fig.update_yaxes(showgrid=True, gridcolor="lightgray", col=2)

        html_path = f"{output_dir}/price_expend_trend.html"
        fig.write_html(html_path, default_width="100%", default_height="100%")
        print(f" -> Success! Price and expenditure HTML saved to {html_path}")

        return df_master

    except Exception:
        print("\n[ERROR] Pipeline failed:")
        traceback.print_exc()


def plot_exports(census_api_key, output_directory):
    print("Plotting: US export trends and trading partners...")
    if not os.path.exists(output_directory):
        os.makedirs(output_directory)

    current_year = datetime.now().year
    latest_year = str(current_year - 1)
    base_year = str(int(latest_year) - 4)

    trade_dictionary = {
        "HVAC": ["841581", "841582", "841861"],
        "Controls & Battery Storage": ["853710", "853720", "850760",
                                       "850720", "850780"],
        "Structure & Envelope": ["680610", "680690", "700800",
                                 "730890", "441899"],
        "PV & Transport": ["854143", "8541", "870380",
                           "870340", "870360"],
        "Computing Benchmarks": ["854231", "8542", "847150", "847130"]
    }

    product_labels = {
        "841581": "Air-to-Air Heat Pumps", "841582": "Standard Central AC",
        "841861": "Hydronic Heat Pumps", "853710": "Smart Building Controls",
        "853720": "Grid/Building Switchgear", "850760": "Li-Ion Storage",
        "850720": "Lead-Acid Backup", "850780": "Other Non-Lithium Storage",
        "680610": "Mineral Insulation", "680690": "Other Insulation Mats",
        "700800": "Insulating Glass", "730890": "Steel Structures",
        "441899": "Wood Joinery", "854143": "Solar Panels (Finished)",
        "8541": "Other Solar & Diodes", "870380": "EVs (Pure Electric)",
        "870340": "Standard Hybrids", "870360": "Plug-in Hybrids",
        "854231": "AI & Logic Chips", "8542": "Other Semiconductors",
        "847150": "Data Center Servers", "847130": "Laptops & Portables"
    }

    subtraction_map = {"8541": "854143", "8542": "854231"}
    codes_to_fetch = [c for sub in trade_dictionary.values() for c in sub]
    trade_endpoint = (
        "https://api.census.gov/data/timeseries/intltrade/exports/hs"
    )

    print(" -> Fetching total US exports trend data...")
    all_rows = []
    for hs in codes_to_fetch:
        params = {
            "get": "ALL_VAL_MO,E_COMMODITY", "E_COMMODITY": hs,
            "COMM_LVL": f"HS{len(hs)}", "time": "from 2013-01",
            "key": census_api_key
        }
        try:
            r = requests.get(trade_endpoint, params=params, timeout=15)
            if r.status_code == 200:
                data = r.json()
                for row in data[1:]:
                    all_rows.append({
                        'Val': float(row[0]), 'HS': str(row[1]),
                        'Date': pd.to_datetime(row[4], format='%Y-%m')
                    })
            time.sleep(0.1)
        except Exception as e:
            print(f"Error on {hs}: {e}")

    if not all_rows:
        print("PIPELINE HALTED: No time-series data retrieved.")
        return

    df_ts = pd.DataFrame(all_rows)
    df_piv = df_ts.pivot_table(
        index='Date', columns='HS', values='Val', aggfunc='sum'
    ).fillna(0)

    for total, sub in subtraction_map.items():
        if total in df_piv.columns and sub in df_piv.columns:
            df_piv[total] = df_piv[total] - df_piv[sub]

    df_clean = df_piv.reset_index().melt(
        id_vars='Date', var_name='HS', value_name='Val'
    )

    final_list = []
    for hs in df_clean['HS'].unique():
        sub = df_clean[df_clean['HS'] == hs].sort_values('Date').copy()
        sub['Smooth'] = sub['Val'].rolling(12).mean() / 1_000_000
        final_list.append(sub)
    df_plot_ts = pd.concat(final_list)

    print(" -> Fetching country-specific data...")
    comp_rows = []

    comp_codes = {
        "841581": "Air-to-Air Heat Pumps",
        "853710": "Smart Building Controls",
        "850760": "Li-Ion Storage",
        "680610": "Mineral Insulation",
        "700800": "Insulating Glass"
    }

    for hs, label in comp_codes.items():
        for yr in [base_year, latest_year]:
            params = {
                "get": "ALL_VAL_MO,CTY_NAME,CTY_CODE", "E_COMMODITY": hs,
                "CTY_CODE": "*", "COMM_LVL": "HS6", "time": yr,
                "key": census_api_key
            }
            r = requests.get(trade_endpoint, params=params)
            if r.status_code == 200:
                data = r.json()
                headers = data[0]
                v_idx, n_idx, c_idx = (
                    headers.index("ALL_VAL_MO"), headers.index("CTY_NAME"),
                    headers.index("CTY_CODE")
                )
                sums = {}
                for row in data[1:]:
                    code_str = str(row[c_idx])
                    if not code_str.isdigit() or not (1000 <= int(code_str) <= 6999):
                        continue
                    v_raw = row[v_idx]
                    v_f = float(v_raw) if v_raw not in [None, '-', ''] else 0.0
                    sums[row[n_idx]] = sums.get(row[n_idx], 0) + v_f
                for c_name, total in sums.items():
                    comp_rows.append({
                        "Label": label, "Year": yr,
                        "Value": total, "Country": c_name
                    })

    if not comp_rows:
        print("❌ PIPELINE HALTED: No composition data retrieved.")
        return

    df_raw = pd.DataFrame(comp_rows)
    df_pivot = df_raw.pivot_table(
        index=['Label', 'Country'], columns='Year', values='Value',
        aggfunc='sum'
    ).reset_index().fillna(0)
    df_pivot.columns = [str(c) for c in df_pivot.columns]

    if base_year not in df_pivot.columns:
        df_pivot[base_year] = 0.0
    if latest_year not in df_pivot.columns:
        df_pivot[latest_year] = 0.0

    df_pivot['Change'] = df_pivot[latest_year] - df_pivot[base_year]

    final_bar_rows = []
    for label in df_pivot['Label'].unique():
        df_sub = df_pivot[df_pivot['Label'] == label].sort_values(
            latest_year, ascending=False
        )
        total_base = df_sub[base_year].sum()
        total_latest = df_sub[latest_year].sum()

        div_base = total_base if total_base > 0 else 1
        div_latest = total_latest if total_latest > 0 else 1

        top_5 = df_sub.head(5)
        for _, row in top_5.iterrows():
            row_dict = row.to_dict()
            row_dict['Share_Latest'] = (row[latest_year] / div_latest) * 100
            row_dict['Growth_Contrib'] = (row['Change'] / div_base) * 100
            final_bar_rows.append(row_dict)

        others_df = df_sub.iloc[5:]
        if not others_df.empty:
            o_base = others_df[base_year].sum()
            o_latest = others_df[latest_year].sum()
            o_change = others_df['Change'].sum()

            final_bar_rows.append({
                'Label': label, 'Country': 'All Other',
                base_year: o_base, latest_year: o_latest, 'Change': o_change,
                'Share_Latest': (o_latest / div_latest) * 100,
                'Growth_Contrib': (o_change / div_base) * 100
            })

    df_bar = pd.DataFrame(final_bar_rows)

    fig = make_subplots(
        rows=2, cols=2, specs=[[{"colspan": 2}, None], [{}, {}]],
        vertical_spacing=0.15, row_heights=[0.70, 0.30],
        horizontal_spacing=0.08,
        subplot_titles=(
            "Monthly Value by Export Category<br>"
            "<sup>Source: Census U.S. Exports of Goods</sup>",
            f"% of {latest_year} Total<br>"
            "<sup>Source: Census U.S. Exports of Goods</sup>",
            f"% Growth, {base_year}-{latest_year}<br>"
            "<sup>Source: Census U.S. Exports of Goods</sup>"
        )
    )

    line_palette = px.colors.qualitative.Alphabet
    all_hs_list = [c for sub in trade_dictionary.values() for c in sub]

    for grp_name, hs_list in trade_dictionary.items():
        for hs in hs_list:
            d = df_plot_ts[
                (df_plot_ts['HS'] == hs) & (df_plot_ts['Date'] >= '2014-01-01')
            ]
            if not d.empty:
                c_idx = all_hs_list.index(hs) % len(line_palette)
                fig.add_trace(go.Scatter(
                    x=d['Date'], y=d['Smooth'], name=product_labels.get(hs, hs),
                    line=dict(width=2.5, color=line_palette[c_idx]),
                    legendgroup=grp_name,
                    legendgrouptitle_text=f"<b>{grp_name}</b>",
                    hovertemplate="$%{y:,.1f}M<extra></extra>", legend="legend"
                ), row=1, col=1)

    bar_colors = px.colors.qualitative.Prism
    u_countries = df_bar['Country'].unique()
    sorted_countries = [
        c for c in u_countries if c != 'All Other'
    ] + ['All Other']

    for idx, country in enumerate(sorted_countries):
        c_sub = df_bar[df_bar['Country'] == country]
        color = ('rgb(180,180,180)' if country == 'All Other'
                 else bar_colors[idx % len(bar_colors)])

        fig.add_trace(go.Bar(
            name=country, x=c_sub['Label'], y=c_sub['Share_Latest'],
            marker_color=color, legend="legend2",
            hovertemplate=(
                "<b>" + country + "</b><br>Share: %{y:.1f}%<extra></extra>"
            )
        ), row=2, col=1)

        fig.add_trace(go.Bar(
            name=country, x=c_sub['Label'], y=c_sub['Growth_Contrib'],
            marker_color=color, showlegend=False, legend="legend2",
            hovertemplate=(
                "<b>" + country + "</b><br>Added to Growth: "
                "%{y:.1f}%<extra></extra>"
            )
        ), row=2, col=2)

    fig.update_layout(
        template="plotly_white", height=1300, barmode='relative',
        hovermode="x unified",
        legend=dict(
            groupclick="toggleitem", traceorder="grouped",
            yanchor="top", y=1.0, xanchor="left", x=1.02
        ),
        legend2=dict(
            title="<b>Country</b>", traceorder="normal",
            yanchor="top", y=0.32, xanchor="left", x=1.02  # Moved up
        ),
        margin={"r": 150, "t": 50, "l": 20, "b": 50}
    )

    fig.update_yaxes(title_text="Value ($M, 12-Mo. Avg.)", row=1, col=1)
    fig.update_yaxes(title_text="% of Total Export Market", row=2, col=1)
    fig.update_yaxes(title_text="% Growth", row=2, col=2)

    custom_x_order = [
        "Air-to-Air Heat Pumps", "Insulating Glass", "Mineral Insulation",
        "Smart Building Controls", "Li-Ion Storage"
    ]

    fig.update_xaxes(
        categoryorder='array', categoryarray=custom_x_order, row=2, col=1
    )
    fig.update_xaxes(
        categoryorder='array', categoryarray=custom_x_order, row=2, col=2
    )

    output_file = f"{output_directory}/exports.html"
    fig.write_html(output_file)
    print(f"Exports HTML complete: {output_file}")


def find_latest_eia_861_year():
    """Finds the latest available EIA-861 data year by checking zip urls."""
    year = pd.Timestamp.now().year
    while year >= 2018:
        url = f"https://www.eia.gov/electricity/data/eia861/zip/f861{year}.zip"
        try:
            r = requests.head(url, timeout=5)
            if r.status_code == 200:
                return year
        except Exception:
            pass
        year -= 1
    return 2023  # Fallback


# ==========================================
# 3. MAIN ORCHESTRATOR
# ==========================================

def main():
    """Main execution entry point."""
    print("=====================================================")
    print("  INITIALIZING PLOTTING PIPELINE")
    print("=====================================================\n")

    load_dotenv()

    bls_key = os.environ.get('BLS_API_KEY')
    eia_key = os.environ.get('EIA_API_KEY')
    bea_key = os.environ.get('BEA_API_KEY')
    ita_key = os.environ.get('ITA_API_KEY')
    census_key = os.environ.get('CENSUS_API_KEY')

    if not all([bls_key, eia_key, bea_key, ita_key, census_key]):
        print(
            "\n[WARNING] One or more API keys are missing from the environment."
        )

    output_dir = "graphics"
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    try:
        latest_eia_year = find_latest_eia_861_year()
        plot_energy_burden(output_dir)
        plot_fuel_price_ratio(eia_key, output_dir)
        plot_permits_construction(census_key, output_dir)
        plot_county_heating_equipment(census_key, output_dir)
        plot_ann_elec_sales(output_dir)
        plot_peak_data(output_dir)
        plot_utility_costs(latest_eia_year, output_dir)
        plot_dsm_comprehensive_dashboard(latest_eia_year, output_dir)
        plot_building_jobs_trend(bls_key, output_dir)
        plot_gdp_by_building_type(bea_key, output_dir)
        plot_ferc_load_growth_forecasts(output_dir)
        plot_insurance_costs(output_dir)
        plot_price_expend_benchmarks(output_dir)
        plot_exports(census_key, output_dir)

        print(f"\nPipeline complete. Visuals saved to ./{output_dir}")
    except Exception as e:
        print(f"\nPIPELINE HALTED DUE TO ERROR: {e}")


if __name__ == "__main__":
    main()
