#!/usr/bin/env python3
"""
master.py

A live-data pipeline for extracting, cleaning, and
visualizing U.S. buildings sector data from federal APIs.
No dummy data is used. Requires valid API keys for BLS, EIA, BEA, ITA,
and the US Census Bureau.
Saves all outputs as static .png files.
"""

import os
import zipfile
import io
import json
from urllib.request import urlopen
import pandas as pd
import requests
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import re
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
import numpy as np

# Ensure clean data handling
pd.set_option('future.no_silent_downcasting', True)


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
    recs_url = (
        "https://www.eia.gov/consumption/residential/"
        "data/2020/csv/recs2020_public_v5.csv"
    )

    # Pull both dollar amounts in one pass
    df = pd.read_csv(
        recs_url,
        usecols=['state_postal', 'TOTALDOL', 'DOLLAREL', 'MONEYPY']
    )

    income_map = {
        1: 2500, 2: 6250, 3: 8750, 4: 11250, 5: 13750,
        6: 17500, 7: 22500, 8: 27500, 9: 32500, 10: 37500,
        11: 45000, 12: 55000, 13: 67500, 14: 87500,
        15: 125000, 16: 175000
    }

    df = df[df['MONEYPY'].isin(income_map.keys())].copy()
    df['Income_Est'] = df['MONEYPY'].map(income_map)

    # Calculate both percentages
    df['Total_Burden_Pct'] = (df['TOTALDOL'] / df['Income_Est']) * 100
    df['Electric_Burden_Pct'] = (df['DOLLAREL'] / df['Income_Est']) * 100

    # Group by state and calculate medians for both
    cols = ['Total_Burden_Pct', 'Electric_Burden_Pct']
    state_burden = df.groupby('state_postal')[cols].median().reset_index()
    state_burden = state_burden.sort_values('Total_Burden_Pct', ascending=True)

    max_burden = state_burden['Total_Burden_Pct'].max()

    # ==========================================
    # BUILD COMBINED DASHBOARD
    # ==========================================
    fig = make_subplots(
        rows=2, cols=2,
        row_heights=[0.3, 0.7],
        vertical_spacing=0.15,  # Increased to create more gap below maps
        specs=[
            [{'type': 'choropleth'}, {'type': 'choropleth'}],  # Top: Maps
            [{'type': 'bar', 'colspan': 2}, None]              # Bottom: Bar
        ],
        subplot_titles=(
            ("Total Energy Burden<br>"
             "<sup>Source: RECS</sup>"),
            ("Electric Energy Burden<br>"
             "<sup>Source: RECS</sup>"),
            ("Total and Electric Energy Burden by State<br>"
             "<sup>Source: RECS</sup>")
        )
    )

    # --- ROW 1: THE MAPS ---
    fig.add_trace(
        go.Choropleth(
            locations=state_burden['state_postal'],
            z=state_burden['Total_Burden_Pct'],
            locationmode="USA-states",
            colorscale="magma",
            zmin=0, zmax=max_burden,
            colorbar=dict(title="Median %", x=0.46, len=0.3, y=0.8),
            hovertemplate=(
                "<b>%{location}</b><br>Total: %{z:.2f}%<extra></extra>"
            )
        ),
        row=1, col=1
    )

    fig.add_trace(
        go.Choropleth(
            locations=state_burden['state_postal'],
            z=state_burden['Electric_Burden_Pct'],
            locationmode="USA-states",
            colorscale="magma",
            zmin=0, zmax=max_burden,
            colorbar=dict(title="Median %", x=1.02, len=0.3, y=0.8),
            hovertemplate=(
                "<b>%{location}</b><br>Elec: %{z:.2f}%<extra></extra>"
            )
        ),
        row=1, col=2
    )

    # --- ROW 2: THE BAR CHART ---
    fig.add_trace(go.Bar(
        y=state_burden['state_postal'],
        x=state_burden['Total_Burden_Pct'],
        name='Total Energy Burden',
        orientation='h',
        marker=dict(color='lightgray'),
        hovertemplate="Total Burden: %{x:.2f}%<extra></extra>"
    ), row=2, col=1)

    fig.add_trace(go.Bar(
        y=state_burden['state_postal'],
        x=state_burden['Electric_Burden_Pct'],
        name='Electric Burden Only',
        orientation='h',
        marker=dict(color='#636EFA'),
        hovertemplate="Electric Burden: %{x:.2f}%<extra></extra>"
    ), row=2, col=1)

    # --- LAYOUT & STYLING ---
    fig.update_layout(
        height=1600,
        barmode='overlay',  # Overlays the electric bars onto total bars
        geo=dict(scope='usa', projection_type='albers usa'),
        geo2=dict(scope='usa', projection_type='albers usa'),
        margin={"r": 20, "t": 60, "l": 20, "b": 100},  # Extra bottom margin
        legend=dict(
            orientation="h",
            yanchor="top",
            y=-0.04,  # Moved below the bar plot to prevent crowding
            xanchor="center",
            x=0.5
        )
    )

    # Add specific axes labels for the bar chart
    fig.update_xaxes(
        title_text="Median Energy Burden (% of Income)",
        domain=[0.15, 0.85],  # Narrowed the bar chart width
        row=2, col=1
    )
    fig.update_yaxes(title_text="State", row=2, col=1)

    html_maps_path = f"{output_dir}/energy_burden_maps_bar.html"
    fig.write_html(
        html_maps_path,
        default_width='95%',
        default_height='100%'
    )
    print(f" -> Success! Energy burden HTML saved to {html_maps_path}")


def plot_fuel_price_ratio(eia_key, output_dir):
    """Plotly version ranking residential and commercial fuel price ratios."""
    print("Plotting: Fuel price ratios by state and sector (EIA API)...")

    def get_elec_data(sector_id, col_name):
        params = {
            "frequency": "annual",
            "data[0]": "price",
            "facets[sectorid][]": sector_id,
            "start": "2018",
            "length": 5000
        }
        df = fetch_eia_v2_data("electricity/retail-sales/data/", params, eia_key)
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
            "frequency": "annual",
            "data[0]": "value",
            "facets[process][]": process_id,
            "start": "2018",
            "length": 5000
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
    # 1 kWh = 0.003412 MMBtu, 1 Mcf ~ 1.032 MMBtu
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

    # ==========================================
    # BUILD COMBINED DASHBOARD
    # ==========================================
    fig = make_subplots(
        rows=2, cols=2,
        row_heights=[0.3, 0.7],
        vertical_spacing=0.15,  # Increased to create more gap below maps
        specs=[
            [{'type': 'choropleth'}, {'type': 'choropleth'}],
            [{'type': 'bar', 'colspan': 2}, None]
        ],
        subplot_titles=(
            (f"Residential Customers ({target_year})<br>"
             "<sup>Source: EIA Surveys</sup>"),
            (f"Commercial Customers ({target_year})<br>"
             "<sup>Source: EIA Surveys</sup>"),
            ("Electric vs. Gas Price Ratio by State<br>"
             "<sup>Source: EIA Surveys</sup>")
        )
    )

    # --- ROW 1: THE MAPS ---
    fig.add_trace(
        go.Choropleth(
            locations=df_final['State'], z=df_final['Ratio_RES'],
            locationmode="USA-states", colorscale="viridis",
            colorbar=dict(title="Elec/Gas<br>Price Ratio", x=0.46,
                          len=0.3, y=0.8),
            hovertemplate="<b>%{location}</b><br>Res: %{z:.2f}x<extra></extra>"
        ), row=1, col=1
    )

    fig.add_trace(
        go.Choropleth(
            locations=df_final['State'], z=df_final['Ratio_COM'],
            locationmode="USA-states", colorscale="plasma",
            colorbar=dict(title="Elec/Gas<br>Price Ratio", x=1.02,
                          len=0.3, y=0.8),
            hovertemplate="<b>%{location}</b><br>Com: %{z:.2f}x<extra></extra>"
        ), row=1, col=2
    )

    # --- ROW 2: THE BAR CHART ---
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

    # --- LAYOUT & STYLING ---
    fig.update_layout(
        height=1600,
        barmode='group',
        geo=dict(scope='usa', projection_type='albers usa'),
        geo2=dict(scope='usa', projection_type='albers usa'),
        margin={"r": 20, "t": 60, "l": 20, "b": 100},  # Extra bottom margin
        legend=dict(
            orientation="h",
            yanchor="top",
            y=-0.04,  # Moved below the bar plot to prevent crowding
            xanchor="center",
            x=0.5
        )
    )

    # Narrow the Bar Chart Domain (pulls the sides in to 15% and 85%)
    fig.update_xaxes(title_text="Price Ratio", domain=[0.15, 0.85], row=2, col=1)
    fig.update_yaxes(title_text="State", row=2, col=1)

    html_maps_path = f"{output_dir}/fuel_price_ratio_maps_bar.html"
    fig.write_html(
        html_maps_path,
        default_width='95%',
        default_height='100%'
    )
    print(f" -> Success! Fuel price HTML saved to {html_maps_path}")


def plot_permits_construction(census_key, output_dir):
    """Permits, construction cost maps, and detailed cost breakdown."""
    print("Plotting: Housing permits and construction costs (Census BPS)...")

    # 1. LOAD GEOJSON
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

    # 2. LOAD BPS DATA (Map data)
    target_year = 2024
    success_bps = False
    while target_year >= 2020:
        year_str = str(target_year)[-2:]
        url_a = f"https://www2.census.gov/econ/bps/County/co{year_str}a.txt"
        url_y = f"https://www2.census.gov/econ/bps/County/co{year_str}12y.txt"

        for url in [url_a, url_y]:
            try:
                df = pd.read_csv(url, dtype=str, on_bad_lines='skip')
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

    # 3. LOAD POPULATION DATA (Map data)
    pop_year = target_year
    success_pop = False
    while pop_year >= 2020:
        p_url = f"https://api.census.gov/data/{pop_year}/acs/acs5"
        p_params = {
            "get": "B01003_001E",
            "for": "county:*",
            "key": census_key
        }
        try:
            resp = requests.get(p_url, params=p_params, timeout=15)
            if resp.status_code == 200:
                p_data = resp.json()
                df_pop = pd.DataFrame(p_data[1:], columns=p_data[0])
                df_pop['FIPS'] = (
                    df_pop['state'].str.zfill(2) +
                    df_pop['county'].str.zfill(3)
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
    df_m = df_m.groupby('FIPS', as_index=False).agg({
        'Name': 'first',
        'Units': 'sum',
        'Value': 'sum',
        'Population': 'sum'
    })

    df_v = df_m[(df_m['Population'] > 0) & (df_m['Units'] > 0)].copy()
    df_v['Permits_1k'] = (df_v['Units'] / df_v['Population']) * 1000
    df_v['Cost'] = df_v['Value'] / df_v['Units']

    max_p = df_v['Permits_1k'].quantile(0.95)
    min_c = df_v['Cost'].min()
    max_c = df_v['Cost'].quantile(0.95)

    # 4. LOAD COST BREAKDOWN DATA (Bar Chart Data)
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
        label = re.sub(r'^[IVX]+\.\s*', '', label)
        label = re.sub(r'\s*\(.*\)', '', label)
        return label.strip()

    row_b = df_overhead.iloc[1]
    cost_const = get_clean_cost(row_b.iloc[5])

    non_const_indices = [0, 2, 3, 4, 5, 6]
    cost_non_const = sum([
        get_clean_cost(df_overhead.iloc[i].iloc[5])
        for i in non_const_indices
    ])

    df1 = pd.DataFrame([
        {'Label': 'Total Construction Costs', 'Cost': cost_const,
         'Group': 'Const'},
        {'Label': 'Non-Construction Costs', 'Cost': cost_non_const,
         'Group': 'Non-Const'}
    ])
    df1 = df1.sort_values('Cost', ascending=False)

    const_indices = [0, 6, 9, 15, 20, 25, 37, 43]
    const_sub = []
    for i in const_indices:
        row = df_full.iloc[i]
        c_val = get_clean_cost(row.iloc[5])
        c_label = get_clean_label(row.iloc[0])
        const_sub.append({'Label': c_label, 'Cost': c_val, 'Group': 'Const'})

    non_const_sub = []
    for i in non_const_indices:
        row = df_overhead.iloc[i]
        c_val = get_clean_cost(row.iloc[5])
        c_label = get_clean_label(row.iloc[0])
        non_const_sub.append({
            'Label': c_label, 'Cost': c_val, 'Group': 'Non-Const'
        })

    df2 = pd.DataFrame(const_sub + non_const_sub)
    df2_const = df2[df2['Group'] == 'Const'].sort_values(
        'Cost', ascending=False
    )
    df2_non = df2[df2['Group'] == 'Non-Const'].sort_values(
        'Cost', ascending=False
    )
    df2_sorted = pd.concat([df2_const, df2_non])

    total_price = cost_const + cost_non_const

    def add_legend_labels(df_source, total):
        df_source['Percent'] = df_source['Cost'] / total * 100
        df_source['LegendLabel'] = df_source.apply(
            lambda x: (
                f"{x['Label']} "
                f"(${x['Cost']/1000:.0f}K - {x['Percent']:.0f}%)"
            ),
            axis=1
        )
        return df_source

    df1 = add_legend_labels(df1, total_price)
    df2_sorted = add_legend_labels(df2_sorted, total_price)

    # Use Matplotlib to generate our color ramps
    cmap_red = plt.get_cmap('Reds')
    reds = [
        mcolors.to_hex(cmap_red(x))
        for x in np.linspace(0.4, 0.9, len(df2_const))
    ]
    cmap_blue = plt.get_cmap('Blues')
    blues = [
        mcolors.to_hex(cmap_blue(x))
        for x in np.linspace(0.4, 0.9, len(df2_non))
    ]
    df2_sorted['Color'] = reds + blues

    # ==========================================
    # 5. BUILD DASHBOARD
    # ==========================================
    fig = make_subplots(
        rows=2, cols=2,
        row_heights=[0.6, 0.4],
        vertical_spacing=0.08,
        specs=[
            [{'type': 'choropleth'}, {'type': 'choropleth'}],
            [{'type': 'bar', 'colspan': 2}, None]
        ],
        subplot_titles=(
            ("New Housing Permits<br>"
             "<sup>Source: Census BPS</sup>"),
            ("New Housing Construction Cost<br>"
             "<sup>Source: Census BPS</sup>"),
            ("Typical New Single Family Home: Sale Price Breakdown<br>"
             "<sup>Source: NAHB</sup><br>")
        )
    )

    # --- MAPS ---
    fig.add_trace(
        go.Choropleth(
            geojson=counties, locations=df_v['FIPS'],
            z=df_v['Permits_1k'], colorscale="Inferno",
            zmin=0, zmax=max_p, marker_line_width=0,
            colorbar=dict(title="Permits/1k", x=0.46, len=0.35, y=0.8),
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
            colorbar=dict(title="Avg Cost ($)", x=1.02, len=0.35, y=0.8),
            customdata=df_v[['Name', 'Units']],
            hovertemplate=(
                "<b>%{customdata[0]}</b><br>"
                "Cost: $%{z:,.0f}<extra></extra>"
            )
        ), row=1, col=2
    )

    # --- BAR CHART ---
    colors1 = {
        'Total Construction Costs': '#E57373',
        'Non-Construction Costs': '#64B5F6'
    }

    # Add High Level Bar
    for _, row in df1.iterrows():
        fig.add_trace(go.Bar(
            x=[row['Cost']], y=['High Level'],
            name=row['LegendLabel'], orientation='h',
            marker=dict(color=colors1.get(row['Label'], '#E57373')),
            legendgroup='High Level',
            legendgrouptitle_text='High Level Summary',
            hovertemplate=(
                f"<b>{row['Label']}</b><br>"
                f"Cost: ${row['Cost']/1000:.0f}K<br>"
                f"Share: {row['Percent']:.1f}%<extra></extra>"
            )
        ), row=2, col=1)

    # Add Detailed Bar
    for _, row in df2_sorted.iterrows():
        fig.add_trace(go.Bar(
            x=[row['Cost']], y=['Detailed'],
            name=row['LegendLabel'], orientation='h',
            marker=dict(color=row['Color']),
            legendgroup='Detailed Breakdown',
            legendgrouptitle_text='Detailed Breakdown',
            hovertemplate=(
                f"<b>{row['Label']}</b><br>"
                f"Cost: ${row['Cost']/1000:.0f}K<br>"
                f"Share: {row['Percent']:.1f}%<extra></extra>"
            )
        ), row=2, col=1)

    # --- LAYOUT & STYLING ---
    fig.update_layout(
        height=1400,
        barmode='stack',
        geo=dict(scope='usa', projection_type='albers usa'),
        geo2=dict(scope='usa', projection_type='albers usa'),
        margin={"r": 20, "t": 60, "l": 20, "b": 100},
        legend=dict(
            orientation="h", yanchor="top", y=-0.05,
            xanchor="center", x=0.5,
            groupclick="toggleitem"
        )
    )

    # Force order of categorical y-axis, add HTML spaces instead of tickpad
    fig.update_yaxes(
        categoryorder='array',
        categoryarray=['Detailed', 'High Level'],
        ticksuffix="&nbsp;&nbsp;&nbsp;&nbsp;",  # Pushes text left using spaces
        row=2, col=1
    )
    fig.update_xaxes(
        domain=[0.15, 0.85],
        row=2, col=1
    )

    html_maps_path = f"{output_dir}/permits_construction_costs.html"
    fig.write_html(html_maps_path, default_width='95%', default_height='100%')
    print(f" -> Success! Construction HTML saved to {html_maps_path}")


def plot_county_heating_equipment(census_key, output_dir):
    """Electric heating penetration and shift to/from electric heating fuel."""
    print("Plotting: County-Level heating equipment (Census ACS)...")

    # 1. Load the GeoJSON file for US Counties required by Plotly
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

    # Helper function to fetch ACS Heating Fuel Data
    def get_heating_data(year):
        url = f"https://api.census.gov/data/{year}/acs/acs5"
        params = {
            "get": "NAME,B25040_001E,B25040_004E",
            "for": "county:*",
            "key": census_key
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
        df = df[mask].copy()
        return df[['FIPS', 'NAME', 'Total_HH', 'Electric_HH']]

    # 2. Fetch 2020 and 2024 Data
    print(" -> Pulling 2020 ACS heating data...")
    df_2020 = get_heating_data(2020)
    print(" -> Pulling 2024 ACS heating data...")
    df_2024 = get_heating_data(2024)

    if df_2020 is None or df_2024 is None:
        print("\n[WARNING] Could not complete API calls. Skipping map.")
        return

    # 3. Apply Connecticut Crosswalk Patch to 2024 Data BEFORE Merging
    ct_crosswalk = {
        '09110': '09003', '09120': '09001', '09130': '09007',
        '09140': '09009', '09150': '09015', '09160': '09005',
        '09170': '09009', '09180': '09011', '09190': '09001'
    }
    df_2024['FIPS'] = df_2024['FIPS'].replace(ct_crosswalk)

    df_2024 = df_2024.groupby('FIPS', as_index=False).agg({
        'NAME': 'first',
        'Total_HH': 'sum',
        'Electric_HH': 'sum'
    })

    # 4. Merge and Calculate the Electrification Shift
    df_merged = pd.merge(
        df_2020, df_2024, on='FIPS', suffixes=('_20', '_24'), how='inner'
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

    # 5. Build the Side-by-Side Choropleth Maps
    fig_maps = make_subplots(
        rows=1, cols=2,
        specs=[[{'type': 'choropleth'}, {'type': 'choropleth'}]],
        subplot_titles=(("Residential Electric Heating Penetration (2024)<br>"
                         "<sup>Source: Census ACS</sup>"),
                        ("Electric Shift From Previous Survey (2020 vs. 2024)<br>"
                         "<sup>Source: Census ACS</sup>"))
    )

    # Left Panel: 2024 Baseline Percentage
    fig_maps.add_trace(
        go.Choropleth(
            geojson=counties,
            locations=df_merged['FIPS'],
            z=df_merged['Pct_Electric_24'],
            colorscale="Viridis",
            zmin=0, zmax=100,
            marker_line_width=0,
            colorbar=dict(title="%", x=0.46, len=0.75),
            customdata=df_merged[['NAME_24', 'Pct_Electric_20']],
            hovertemplate=(
                "<b>%{customdata[0]}</b><br>"
                "2020 Base: %{customdata[1]:.1f}%<br>"
                "2024 Base: <b>%{z:.1f}%</b><extra></extra>"
            )
        ),
        row=1, col=1
    )

    # Right Panel: The Shift
    fig_maps.add_trace(
        go.Choropleth(
            geojson=counties,
            locations=df_merged['FIPS'],
            z=df_merged['Shift_Pct'],
            colorscale="RdBu",
            zmin=-abs_max, zmax=abs_max,
            marker_line_width=0,
            colorbar=dict(title="%", x=1.02, len=0.75),
            customdata=df_merged[
                ['NAME_24', 'Pct_Electric_20', 'Pct_Electric_24']
            ],
            hovertemplate=(
                "<b>%{customdata[0]}</b><br>"
                "2020 Base: %{customdata[1]:.1f}%<br>"
                "2024 Base: %{customdata[2]:.1f}%<br>"
                "Net Shift: <b>%{z:+.2f}%</b><extra></extra>"
            )
        ),
        row=1, col=2
    )

    fig_maps.update_layout(
        geo=dict(scope='usa', projection_type='albers usa'),
        geo2=dict(scope='usa', projection_type='albers usa'),
        margin={"r": 0, "t": 60, "l": 0, "b": 0}
    )

    # Save the Interactive HTML
    html_path = f"{output_dir}/heating_equip_map.html"
    fig_maps.write_html(html_path, default_width='95%', default_height='70vh')
    print(f" -> Success! Heating equipment map HTML saved to {html_path}")


def plot_ann_elec_sales(output_dir):
    """Annual electricity demand and change over time."""
    print("Plotting: Annual electricity demand growth (EIA 861)...")

    # State Centroids for Map Plotting
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
            f"https://www.eia.gov/electricity/data/eia861/archive/zip/f861{year}.zip"
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
                target = next((f for f in z.namelist() if 'sales_ult_cust' in f.lower()
                               and not f.startswith('~')), None)
                if not target:
                    return None

                df = pd.read_excel(z.open(target), header=None)
                mask = df.apply(lambda row: row.astype(str).str.contains(
                    'Utility Number|Utility ID', case=False, na=False).any(), axis=1)
                header_idx = mask.index[mask][0]

                super_row_idx = -1
                for i in range(header_idx, -1, -1):
                    if df.iloc[i].astype(str).str.contains(
                            'RESIDENTIAL', case=False, na=False).any():
                        super_row_idx = i
                        break

                if super_row_idx != -1:
                    top_row = df.iloc[super_row_idx].astype(str).str.strip().replace(
                        ['nan', 'None', ''], pd.NA).ffill().fillna('')
                    bottom_row = df.iloc[header_idx].astype(str).str.strip().replace(
                        ['nan', 'None'], '')
                    combined_cols = top_row + "_" + bottom_row
                else:
                    combined_cols = df.iloc[header_idx].astype(str).replace('nan', '')

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
                    ['Utility_Num', 'Utility_Name', 'State'], as_index=False).agg({
                        'Res_Sales': 'sum', 'Com_Sales': 'sum',
                        'Ind_Sales': 'sum', 'Tra_Sales': 'sum'})
        except Exception as e:
            print(f"Error: {e}")
            return None

    # 1. Fetch 3 years of data
    df_23 = extract_sales_data(2023)
    df_21 = extract_sales_data(2021)
    df_18 = extract_sales_data(2018)

    if any(df is None for df in [df_23, df_21, df_18]):
        return

    # 2. Triple Merge
    df_m = pd.merge(df_18, df_21, on=['Utility_Num', 'State'],
                    suffixes=('_18', '_21'))
    df_m = pd.merge(df_m, df_23, on=['Utility_Num', 'State'])

    # Fix naming after double merge
    if 'Utility_Name' in df_m.columns:
        df_m = df_m.rename(columns={'Utility_Name': 'Utility_Name_23'})

    # Calculate Utility-level Totals
    for y in ['18', '21', '23']:
        cols = [f'Res_Sales_{y}', f'Com_Sales_{y}',
                f'Ind_Sales_{y}', f'Tra_Sales_{y}']
        # Map 2023 columns which won't have suffixes
        if y == '23':
            cols = ['Res_Sales', 'Com_Sales', 'Ind_Sales', 'Tra_Sales']
        df_m[f'Total_{y}'] = df_m[cols].sum(axis=1)

    # 3. State-Level Aggregates
    state_all = df_m.groupby('State').agg({
        'Total_18': 'sum', 'Total_21': 'sum', 'Total_23': 'sum',
        'Res_Sales': 'sum', 'Com_Sales': 'sum', 'Ind_Sales': 'sum',
        'Tra_Sales': 'sum', 'Res_Sales_18': 'sum', 'Com_Sales_18': 'sum',
        'Ind_Sales_18': 'sum', 'Tra_Sales_18': 'sum'
    }).reset_index()

    # State Growth Rates
    state_all['State_5yr'] = (
        (state_all['Total_23'] - state_all['Total_18']) /
        (state_all['Total_18'] + 1)
    ) * 100
    state_all['State_2yr'] = (
        (state_all['Total_23'] - state_all['Total_21']) /
        (state_all['Total_21'] + 1)
    ) * 100

    # Sector Contributions for the Waterfall (using 5yr as the baseline)
    for s in ['Res', 'Com', 'Ind', 'Tra']:
        state_all[f'{s}_Contrib'] = (
            (state_all[f'{s}_Sales'] - state_all[f'{s}_Sales_18']) /
            (state_all['Total_18'] + 1)
        ) * 100

    # 4. Largest Utility Metrics
    df_leaders = df_m.sort_values(
        ['State', 'Total_23'], ascending=[True, False]
    ).groupby('State').head(1).copy()

    df_leaders['Util_5yr'] = (
        (df_leaders['Total_23'] - df_leaders['Total_18']) /
        (df_leaders['Total_18'] + 1)
    ) * 100
    df_leaders['Util_2yr'] = (
        (df_leaders['Total_23'] - df_leaders['Total_21']) /
        (df_leaders['Total_21'] + 1)
    ) * 100

    # 5. Mapping Prep
    df_plot = pd.merge(
        state_all,
        df_leaders[['State', 'Utility_Name_23', 'Util_5yr',
                    'Util_2yr', 'Total_23']],
        on='State', suffixes=('_State', '_Leader')
    )

    def apply_loc(row):
        st = str(row['State']).upper().strip()
        if st in state_centroids:
            return pd.Series({'Lat': state_centroids[st][0],
                              'Lon': state_centroids[st][1]})
        return pd.Series({'Lat': None, 'Lon': None})

    df_plot[['Lat', 'Lon']] = df_plot.apply(apply_loc, axis=1).dropna()

    # ENHANCED HOVER WITH ACCELERATION METRICS
    def make_hover(row):
        line1 = f"<b>STATE: {row['State']}</b><br>"
        line2 = f"Total Sales: {row['Total_23_State']:,.0f} MWh<br>"
        line3 = f"State 5-yr Growth: <b>{row['State_5yr']:+.1f}%</b><br>"
        line4 = f"State 2-yr Growth: <b>{row['State_2yr']:+.1f}%</b><br>---<br>"
        line5 = f"Market Leader: {row['Utility_Name_23']}<br>"
        line6 = f"Leader 5-yr Growth: <b>{row['Util_5yr']:+.1f}%</b><br>"
        line7 = f"Leader 2-yr Growth: <b>{row['Util_2yr']:+.1f}%</b>"
        return f"{line1}{line2}{line3}{line4}{line5}{line6}{line7}"

    df_plot['HoverText'] = df_plot.apply(make_hover, axis=1)

    # 6. Build Plot
    fig = make_subplots(
        rows=2, cols=1, row_heights=[0.6, 0.4], vertical_spacing=0.1,
        specs=[[{'type': 'scattergeo'}], [{'type': 'bar'}]],
        subplot_titles=(
            ("Annual Electricity Sales by State (2023) and Demand Growth (2018-2023)<br>"
             "<sup>Source: EIA 861</sup>"),
            ("States with Highest Growth in Total Sales (2018-2023), by Sector<br>"
             "<sup>Source: EIA 861</sup>")
        )
    )

    # Map
    sizeref = 2. * df_plot['Total_23_State'].max() / (65 ** 2)
    fig.add_trace(go.Scattergeo(
        lon=df_plot['Lon'], lat=df_plot['Lat'], text=df_plot['HoverText'],
        hoverinfo='text',
        showlegend=False,  # FIX: explicitly hide map from legend
        marker=dict(
            size=df_plot['Total_23_State'], sizemode='area', sizeref=sizeref,
            color=df_plot['State_5yr'], colorscale='RdBu', cmin=-20, cmax=20,
            showscale=True, colorbar=dict(title="5-yr Growth %", x=0.9,
                                          len=0.5, y=0.75)
        )
    ), row=1, col=1)

    # Waterfall
    state_sorted = state_all.sort_values('State_5yr', ascending=False).head(20)
    colors = {'Res': '#1f77b4', 'Com': '#ff7f0e',
              'Ind': '#2ca02c', 'Tra': '#d62728'}
    sectors = [('Res', 'Residential'), ('Com', 'Commercial'),
               ('Ind', 'Industrial'), ('Tra', 'Transportation')]

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
        barmode='relative', hovermode='x unified', height=1100,
        geo=dict(scope='usa', projection_type='albers usa', showland=True,
                 landcolor='rgb(240, 240, 240)'),
        yaxis2=dict(title="% Net 5-yr Growth"),
        legend=dict(orientation="h", yanchor="bottom", y=-0.1,
                    xanchor="center", x=0.5)
    )

    html_path = f"{output_dir}/annual_sales.html"
    fig.write_html(html_path)
    print(f" -> Success! Annual sales plots saved to {html_path}")


def extract_peak_data(year):
    """Targets Operational_Data and flattens multi-row headers."""
    urls = [
        f"https://www.eia.gov/electricity/data/eia861/zip/f861{year}.zip",
        f"https://www.eia.gov/electricity/data/eia861/archive/zip/f861{year}.zip"
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

            idx_uid = find_idx(['utility', 'number']) or \
                find_idx(['utility', 'id'])
            idx_st = find_idx(['state'])
            idx_sum = find_idx(['summer', 'peak']) or \
                find_idx(['summer', 'demand']) or find_idx(['summer', 'max'])
            idx_win = find_idx(['winter', 'peak']) or \
                find_idx(['winter', 'demand']) or find_idx(['winter', 'max'])

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

    # Static dictionary of US State Centroids
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

    df_23 = extract_peak_data(2023)
    df_18 = extract_peak_data(2018)
    if df_23 is None or df_18 is None:
        return

    # 1. Merge and Filter
    df_m = pd.merge(
        df_18, df_23, on=['Util_ID', 'State'], suffixes=('_18', '_23')
    )
    valid_us_states = set(state_centroids.keys())

    st = df_m.groupby('State').agg({
        'Summer_MW_23': 'sum', 'Winter_MW_23': 'sum',
        'Summer_MW_18': 'sum', 'Winter_MW_18': 'sum'
    }).reset_index()
    st = st[st['State'].isin(valid_us_states)].copy()

    # 2. Calculate Ratios and Growth
    st['Ratio'] = st['Summer_MW_23'] / (st['Winter_MW_23'] + 1)
    st['Max_MW'] = st[['Summer_MW_23', 'Winter_MW_23']].max(axis=1)

    st['Winter_Growth'] = (
        (st['Winter_MW_23'] - st['Winter_MW_18']) / (st['Winter_MW_18'] + 1)
    ) * 100

    st['Summer_Growth'] = (
        (st['Summer_MW_23'] - st['Summer_MW_18']) / (st['Summer_MW_18'] + 1)
    ) * 100

    # 3. Setup Layout
    fig = make_subplots(
        rows=2, cols=2,
        row_heights=[0.6, 0.4],
        vertical_spacing=0.12,
        horizontal_spacing=0.1,
        specs=[
            [{"type": "scattergeo", "colspan": 2}, None],
            [{"type": "bar"}, {"type": "bar"}]
        ],
        subplot_titles=(
            ("Peak Demand Seasonality<br>"
             "<sup>Source: EIA 861</sup>"),
            ("States with Highest Growth in Winter Peak Demand<br>"
             "<sup>Source: EIA 861</sup>"),
            ("States with Highest Growth in Summer Peak Demand<br>"
             "<sup>Source: EIA 861</sup>")
        )
    )

    # --- ROW 1: THE MAP ---
    sizeref = 2. * st['Max_MW'].max() / (60 ** 2)
    lats = st['State'].map(lambda x: state_centroids[x][0])
    lons = st['State'].map(lambda x: state_centroids[x][1])

    # Build multi-line text string
    hover_text = (
        st['State'] + "<br>Max Peak: " +
        st['Max_MW'].apply(lambda x: f"{x:,.0f} MW") +
        "<br>Ratio: " + st['Ratio'].round(2).astype(str)
    )

    fig.add_trace(go.Scattergeo(
        lon=lons, lat=lats,
        marker=dict(
            size=st['Max_MW'], sizemode='area', sizeref=sizeref,
            color=st['Ratio'], colorscale='RdYlBu_r',
            cmin=0.8, cmid=1.0, cmax=1.2,
            showscale=True,
            colorbar=dict(
                title="Summer/Winter<br>Peak Ratio", thickness=15,
                len=0.4, y=0.8, x=0.95
            )
        ),
        text=hover_text,
        hoverinfo='text', showlegend=False
    ), row=1, col=1)

    # --- ROW 2, LEFT: WINTER GROWTH ---
    st_winter = st.sort_values('Winter_Growth', ascending=False).head(15)
    fig.add_trace(go.Bar(
        x=st_winter['State'], y=st_winter['Winter_Growth'],
        marker_color='#1f77b4', name='Winter Growth',
        hovertemplate="State: %{x}<br>Winter Growth: %{y:+.1f}%<extra></extra>"
    ), row=2, col=1)

    # --- ROW 2, RIGHT: SUMMER GROWTH ---
    st_summer = st.sort_values('Summer_Growth', ascending=False).head(15)
    fig.add_trace(go.Bar(
        x=st_summer['State'], y=st_summer['Summer_Growth'],
        marker_color='#ff7f0e', name='Summer Growth',
        hovertemplate="State: %{x}<br>Summer Growth: %{y:+.1f}%<extra></extra>"
    ), row=2, col=2)

    # 4. Final Polish
    fig.update_layout(
        height=1000, margin={"r": 30, "t": 80, "l": 30, "b": 50},
        showlegend=False,
        geo=dict(
            scope='usa', projection_type='albers usa',
            showland=True, landcolor='rgb(245, 245, 245)'
        )
    )

    fig.update_yaxes(title_text="% Growth (2018-23)", row=2, col=1)
    fig.update_yaxes(title_text="% Growth (2018-23)", row=2, col=2)

    html_path = f"{output_dir}/peak_demand.html"
    fig.write_html(html_path)
    print(f" -> Success! Peak demand plots saved to {html_path}")


def generate_eia_mapping_df(year=2023):
    """Fetches EIA-861 master Utility-to-State mapping."""
    base_urls = [
        f"https://www.eia.gov/electricity/data/eia861/zip/f861{year}.zip",
        f"https://www.eia.gov/electricity/data/eia861/archive/zip/f861{year}.zip"
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
            index='State', columns='pillar', values='dollar_value', aggfunc='sum'
        ).fillna(0).reset_index()
        top_s['Total'] = top_s[['Generation', 'Transmission', 'Distribution']]\
            .sum(axis=1)
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


def plot_utility_costs(eia_df, output_dir):
    """Utility annual expenditures in generation, transmission, and distribution."""
    print("Plotting: Utility expenditures (FERC 1/PUDL)...")
    top_s, ca_t, ly = fetch_historical_om_ca(eia_df)
    if top_s is None:
        return

    pillars = ['Generation', 'Transmission', 'Distribution']
    colors = {'Generation': '#1f77b4', 'Transmission': '#ff7f0e', 'Distribution': '#2ca02c'}

    fig = make_subplots(
        rows=2, cols=1, vertical_spacing=0.12,
        subplot_titles=(
            (f"States with Highest Utility O&M Costs ({ly})<br>"
             "<sup>Source: FERC Form 1 via PUDL</sup>"),
            ("CA 10-Year Utility O&M Cost Trend<br>"
             "<sup>Source: FERC Form 1 via PUDL</sup>"))
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
    fig.write_html(html_path)
    print(f" -> Success! Utility cost plots saved to {html_path}")


def fetch_dsm_detailed(year):
    """Fetches Total MW and Sector-level MW (Res, Com, Ind, Trans)."""
    base_urls = [
        f"https://www.eia.gov/electricity/data/eia861/zip/f861{year}.zip",
        f"https://www.eia.gov/electricity/data/eia861/archive/zip/f861{year}.zip"
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
                    # EE Indices: Res=10, Com=11, Ind=12, Trans=13, Total=14
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
                    # DR Pot Indices: 15,16,17,18,19 | Actual=24
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

    # Merge, keeping names from both sheets
    df_combined = pd.merge(
        df_ee, df_dr, on=['Utility ID', 'State'],
        how='outer', suffixes=('', '_dr')
    )
    df_combined['Utility'] = df_combined['Utility'].fillna(
        df_combined['Utility_dr']
    ).fillna("Unknown Utility")

    df_combined = df_combined.drop(columns=['Utility_dr'])
    df_combined = df_combined.infer_objects(copy=False).fillna(0)

    # Add year suffix to all numeric columns
    rename_dict = {
        c: f"{c}_{year}" for c in df_combined.columns
        if c not in ['Utility ID', 'Utility', 'State']
    }
    return df_combined.rename(columns=rename_dict)


def plot_dsm_comprehensive_dashboard(year, output_dir):
    print("Plotting: DSM potential (EIA 861)...")
    base_year = 2018
    df_old = get_dsm_snapshot(base_year)
    df_new = get_dsm_snapshot(year)

    if df_old is None or df_new is None:
        return

    # 1. Merge Years
    cols_to_keep = ['Utility ID', 'State'] + [
        c for c in df_old.columns if str(base_year) in c
    ]
    df_growth = pd.merge(
        df_new, df_old[cols_to_keep], on=['Utility ID', 'State'], how='left'
    ).infer_objects(copy=False).fillna(0)

    # Calculate State-level Aggregates (Totals + Sectors)
    agg_dict = {
        c: 'sum' for c in df_growth.columns
        if str(year) in c or str(base_year) in c
    }
    state_stats = df_growth.groupby('State').agg(agg_dict).reset_index()

    # 2. Calculate Growth Metrics (ABSOLUTE MW + Percentages for Hovers)
    for sect in ['Res', 'Com', 'Ind', 'Trans']:
        state_stats[f'EE_Gr_{sect}'] = (
            state_stats[f'EE_{sect}_{year}'] -
            state_stats[f'EE_{sect}_{base_year}']
        )
        state_stats[f'DR_Gr_{sect}'] = (
            state_stats[f'DR_Pot_{sect}_{year}'] -
            state_stats[f'DR_Pot_{sect}_{base_year}']
        )

    # Absolute Total Growth
    state_stats['EE_State_Growth'] = (
        state_stats[f'EE_Total_{year}'] - state_stats[f'EE_Total_{base_year}']
    )
    state_stats['DR_State_Growth'] = (
        state_stats[f'DR_Pot_Total_{year}'] -
        state_stats[f'DR_Pot_Total_{base_year}']
    )

    # Percentage Math (Just for the Map Hovers)
    def calc_pct(new, old):
        if old > 0:
            return int(round(((new - old) / old) * 100))
        return 100 if new > 0 else 0

    state_stats['EE_State_Pct'] = state_stats.apply(
        lambda r: calc_pct(r[f'EE_Total_{year}'], r[f'EE_Total_{base_year}']),
        axis=1
    ).apply(lambda x: f"{x:+d}")

    state_stats['DR_State_Pct'] = state_stats.apply(
        lambda r: calc_pct(
            r[f'DR_Pot_Total_{year}'], r[f'DR_Pot_Total_{base_year}']
        ),
        axis=1
    ).apply(lambda x: f"{x:+d}")

    state_stats['DR_Util_Pct'] = (
        state_stats[f'DR_Act_Total_{year}'] /
        state_stats[f'DR_Pot_Total_{year}'] * 100
    ).fillna(0).round(0).astype(int)

    # Top Utility Logic for Hovers
    def get_top_util_pct(state, val_col, old_col):
        sub = df_growth[df_growth['State'] == state]
        if sub.empty:
            return "N/A", 0.0, "+0"
        top = sub.sort_values(val_col, ascending=False).iloc[0]
        pct_str = f"{calc_pct(top[val_col], top[old_col]):+d}"
        return str(top['Utility']), float(top[val_col]), pct_str

    ee_meta = state_stats['State'].apply(
        lambda x: get_top_util_pct(
            x, f'EE_Total_{year}', f'EE_Total_{base_year}'
        )
    )
    state_stats[['Top_EE_Name', 'Top_EE_Val', 'Top_EE_Str']] = pd.DataFrame(
        ee_meta.tolist(), index=state_stats.index
    )

    dr_meta = state_stats['State'].apply(
        lambda x: get_top_util_pct(
            x, f'DR_Pot_Total_{year}', f'DR_Pot_Total_{base_year}'
        )
    )
    state_stats[['Top_DR_Name', 'Top_DR_Val', 'Top_DR_Str']] = pd.DataFrame(
        dr_meta.tolist(), index=state_stats.index
    )

    # 3. Prepare Top 15 Data for Bar Charts
    top15_ee = state_stats.sort_values(
        'EE_State_Growth', ascending=False
    ).head(15)
    top15_dr = state_stats.sort_values(
        'DR_State_Growth', ascending=False
    ).head(15)

    # 4. Build 2x2 Subplots
    fig = make_subplots(
        rows=2, cols=2,
        row_heights=[0.6, 0.4], vertical_spacing=0.1,
        specs=[
            [{"type": "geo"}, {"type": "geo"}],
            [{"type": "xy"}, {"type": "xy"}]
        ],
        subplot_titles=(
            ("Energy Efficiency Avoided Peak<br>"
             "<sup>Source: EIA 861</sup>"),
            ("Demand Response Avoided Peak (Potential and Actual)<br>"
             "<sup>Source: EIA 861</sup>"),
            (f"States with Highest EE Growth, by Sector ({base_year}-{year})<br>"
             "<sup>Source: EIA 861</sup>"),
            (f"States with Highest DR Potential Growth, by Sector ({base_year}-{year}<br>"
             "<sup>Source: EIA 861</sup>")
        )
    )

    b_size = 1.5

    # --- ROW 1: MAPS ---
    hover_ee = (
        "<b>%{location}</b><br>State Total: %{marker.size:.1f} MW<br>"
        "5yr Growth: %{customdata[0]}%<br><br>Top Utility: %{customdata[1]}<br>"
        "Utility Potential: %{customdata[2]:.1f} MW<br>"
        "Utility Growth: %{customdata[3]}%<extra></extra>"
    )

    fig.add_trace(go.Scattergeo(
        locations=state_stats['State'], locationmode='USA-states',
        marker=dict(size=state_stats[f'EE_Total_{year}'], sizemode='area',
                    sizeref=b_size, color='rgba(31, 119, 180, 0.7)',
                    line=dict(width=1, color='white')),
        customdata=state_stats[
            ['EE_State_Pct', 'Top_EE_Name', 'Top_EE_Val', 'Top_EE_Str']
        ],
        hovertemplate=hover_ee, name='EE Maps', showlegend=False
    ), row=1, col=1)

    hover_dr = (
        "<b>%{location} (Potential)</b><br>State Potential: "
        "%{marker.size:.1f} MW<br>5yr Growth: %{customdata[0]}%<br><br>"
        "Top Utility: %{customdata[1]}<br>Utility Potential: "
        "%{customdata[2]:.1f} MW<br>Utility Growth: %{customdata[3]}%"
        "<extra></extra>"
    )

    fig.add_trace(go.Scattergeo(
        locations=state_stats['State'], locationmode='USA-states',
        marker=dict(size=state_stats[f'DR_Pot_Total_{year}'],
                    sizemode='area', sizeref=b_size,
                    color='rgba(144, 238, 144, 0.4)', line=dict(width=0)),
        customdata=state_stats[
            ['DR_State_Pct', 'Top_DR_Name', 'Top_DR_Val', 'Top_DR_Str']
        ],
        hovertemplate=hover_dr, name='DR Maps', showlegend=False
    ), row=1, col=2)

    fig.add_trace(go.Scattergeo(
        locations=state_stats['State'], locationmode='USA-states',
        marker=dict(size=state_stats[f'DR_Act_Total_{year}'],
                    sizemode='area', sizeref=b_size,
                    color='rgba(44, 160, 44, 0.9)',
                    line=dict(width=1, color='white')),
        customdata=state_stats[['DR_Util_Pct']],
        hovertemplate=(
            "<b>%{location} (Actual)</b><br>"
            "Actual MW Called: %{marker.size:.1f} MW<br>"
            "Utilization: %{customdata[0]}%<extra></extra>"
        ),
        showlegend=False
    ), row=1, col=2)

    # --- ROW 2: ABSOLUTE MW STACKED BARS ---
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

    # 5. Global Layout Settings
    geo_config = dict(
        scope='usa', projection_type='albers usa', showland=True,
        landcolor='rgb(240, 240, 240)', subunitcolor='white'
    )

    fig.update_layout(
        showlegend=True,
        geo=dict(**geo_config, domain={'x': [0, 0.49]}),
        geo2=dict(**geo_config, domain={'x': [0.51, 1]}),
        barmode='relative',
        legend=dict(
            orientation="h", yanchor="top", y=-0.08,
            xanchor="center", x=0.5
        ),
        margin={"r": 10, "t": 50, "l": 10, "b": 70},
        height=850
    )

    fig.update_yaxes(title_text="5-Year Growth (MW)", row=2, col=1)
    fig.update_yaxes(title_text="5-Year Growth (MW)", row=2, col=2)
    html_path = f"{output_dir}/dsm_potential.html"
    fig.write_html(html_path)
    print(f"-> Success! DSM potential plots saved to {html_path}")


def plot_building_jobs_trend(bls_key, output_dir):
    """Buildings-related jobs trend."""
    print("Plotting: Buildings jobs (BLS)...")

    # Define the CEU (Unadjusted) Series IDs for all sub-sectors
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

    # Assign legend groups for cleaner Plotly toggling
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

    # Hardcode distinct colors to avoid repeating defaults
    colors = [
        '#1f77b4', '#ff7f0e', '#2ca02c', '#d62728',
        '#9467bd', '#8c564b', '#e377c2', '#7f7f7f',
        '#bcbd22', '#17becf', '#393b79', '#5254a3',
        '#6b6ecf', '#9c9ede'
    ]

    # We now have exactly 14 valid series, so we use range(14)
    color_dict = {list(group_map.keys())[i]: colors[i] for i in range(14)}

    headers = {'Content-type': 'application/json'}
    data = json.dumps({
        "seriesid": list(series_map.keys()),
        "startyear": "2005",
        "endyear": "2024",
        "registrationkey": bls_key
    })

    try:
        url = 'https://api.bls.gov/publicAPI/v2/timeseries/data/'
        req = requests.post(url, data=data, headers=headers, timeout=30)
        req.raise_for_status()
        json_data = req.json()
    except Exception as e:
        print(f"\n[WARNING] BLS API fetch failed: {e}")
        return

    if json_data.get('status') != 'REQUEST_SUCCEEDED':
        err = json_data.get('message')
        print(f"\n[WARNING] BLS API Error: {err}")
        return

    records = []
    for series in json_data['Results']['series']:
        series_id = series['seriesID']
        series_name = series_map.get(series_id, series_id)

        for item in series['data']:
            year = item['year']
            period = item['period']

            if period == 'M13':
                continue

            value = float(item['value'])
            month = period.replace('M', '')
            date_str = f"{year}-{month}-01"

            records.append({
                'Date': date_str,
                'Job Category': series_name,
                'Legend Group': group_map.get(series_name, 'Other'),
                'Employees (Thousands)': value
            })

    df = pd.DataFrame(records)
    if df.empty:
        print(" -> [WARNING] No data parsed from BLS.")
        return

    df['Date'] = pd.to_datetime(df['Date'])
    df = df.sort_values(['Job Category', 'Date'])

    # Apply 12-month rolling average to de-seasonalize the unadjusted data
    df['Smoothed Jobs'] = df.groupby('Job Category')[
        'Employees (Thousands)'
    ].transform(lambda x: x.rolling(12, min_periods=1).mean())

    # Filter to 2006+ so the rolling average has time to "warm up"
    df = df[df['Date'] >= '2006-01-01'].copy()

    # Build the Plotly line chart
    fig = go.Figure()

    # We loop through the groups first so they appear organized in the legend
    for grp in df['Legend Group'].unique():
        df_group = df[df['Legend Group'] == grp]
        for category in df_group['Job Category'].unique():
            df_cat = df_group[df_group['Job Category'] == category]
            fig.add_trace(go.Scatter(
                x=df_cat['Date'],
                y=df_cat['Smoothed Jobs'],
                mode='lines',
                name=category,
                line=dict(width=2, color=color_dict.get(category)),
                legendgroup=grp,
                legendgrouptitle_text=f"<b>{grp}</b>",
                hovertemplate=(
                    f"<b>{category}</b><br>"
                    "Date: %{x|%b %Y}<br>"
                    "Jobs: %{y:,.1f}K<extra></extra>"
                )
            ))

    fig.update_layout(
        title=(
            "Trends in Buildings-related Jobs (2006-2024)<br>"
            "<sup>Source: BLS; 12-Month Trailing Average</sup>"
        ),
        xaxis_title="Year",
        yaxis_title="Total Employees (Thousands)",
        template="plotly_white",
        legend=dict(
            orientation="v",  # Switched to vertical because of the 5 groups
            yanchor="top",
            y=1.0,
            xanchor="left",
            x=1.02,           # Placed to the right of the plot
            groupclick="toggleitem"
        ),
        hovermode="x unified",
        margin=dict(r=250, t=80, l=20, b=40),  # Expanded right margin for legend
        height=850
    )

    html_path = f"{output_dir}/building_jobs_trend.html"
    fig.write_html(html_path, default_width='100%', default_height='100%')
    print(f" -> Success! Buildings jobs HTML saved to {html_path}")


def plot_gdp_by_building_type(bea_key, output_dir):
    """Trends in buildings activity contribution to GDP."""
    print("Plotting: Buildings GDP contribution (BEA API)...")

    if not bea_key:
        print("\n[WARNING] BEA API key is missing. Skipping GDP plot.")
        return

    # BEA API Parameters for GDP by Industry (Value Added)
    url = "https://apps.bea.gov/api/data/"
    params = {
        "UserID": bea_key,
        "method": "GetData",
        "datasetname": "GdpByIndustry",
        "TableID": "1",        # Table 1: Value Added by Industry
        "Frequency": "A",      # Annual
        "Year": "ALL",
        "Industry": "ALL",
        "ResultFormat": "JSON"
    }

    try:
        req = requests.get(url, params=params, timeout=30)
        req.raise_for_status()
        data = req.json()
    except Exception as e:
        print(f"\n[WARNING] BEA API fetch failed: {e}")
        return

    # Robust JSON Parsing for BEA API Quirks
    results_node = data.get('BEAAPI', {}).get('Results', {})

    # Check if the API returned an explicit error message
    if isinstance(results_node, dict) and 'Error' in results_node:
        err_msg = results_node['Error'].get('ErrorDetail', results_node['Error'])
        print(f"\n[WARNING] BEA API Error: {err_msg}")
        return

    try:
        # GdpByIndustry sometimes wraps Results in a list
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

    # Convert values and filter for the last 20 years
    df['DataValue'] = pd.to_numeric(df['DataValue'], errors='coerce')
    df['Year'] = pd.to_numeric(df['Year'], errors='coerce')
    current_year = 2023  # Using 2023 as the latest fully revised annual year
    df = df[(df['Year'] >= (current_year - 20)) & (df['Year'] <= current_year)]

    # Map mutually exclusive NAICS equivalents to our 3 building types
    mapping = {
        # --- RESIDENTIAL ---
        '53': 'Residential (Real Estate & Housing)',
        # --- COMMERCIAL (Service Economy) ---
        '44RT': 'Commercial (Offices, Retail, Services)',  # Retail Tradef
        '51': 'Commercial (Offices, Retail, Services)',    # Information
        '52': 'Commercial (Offices, Retail, Services)',    # Finance & Insurance
        '54': 'Commercial (Offices, Retail, Services)',    # Professional
        '55': 'Commercial (Offices, Retail, Services)',    # Management
        '56': 'Commercial (Offices, Retail, Services)',    # Admin/Waste
        '61': 'Commercial (Offices, Retail, Services)',    # Education
        '62': 'Commercial (Offices, Retail, Services)',    # Healthcare
        '71': 'Commercial (Offices, Retail, Services)',    # Arts/Entertainment
        '72': 'Commercial (Offices, Retail, Services)',    # Accommodation/Food
        '81': 'Commercial (Offices, Retail, Services)',    # Other Services
        'G': 'Commercial (Offices, Retail, Services)',     # Government
        # --- INDUSTRIAL / Other ---
        '11': 'Industrial / Other',                      # Agriculture
        '21': 'Industrial / Other',                      # Mining
        '22': 'Industrial / Other',                      # Utilities
        '23': 'Industrial / Other',                      # Construction
        '31G': 'Industrial / Other',                     # Manufacturing
        '42': 'Industrial / Other',                      # Wholesale Trade
        '48TW': 'Industrial / Other'                     # Transport/Warehouse
    }

    df_filtered = df[df['Industry'].isin(mapping.keys())].copy()
    df_filtered['Category'] = df_filtered['Industry'].map(mapping)

    # Aggregate by Year and Category
    df_agg = df_filtered.groupby(['Year', 'Category'])['DataValue'].sum()
    df_agg = df_agg.reset_index()

    # Calculate Total GDP per year for percentage hovers
    total_gdp = df_agg.groupby('Year')['DataValue'].sum().reset_index()
    total_gdp.rename(columns={'DataValue': 'Total_GDP'}, inplace=True)
    df_agg = pd.merge(df_agg, total_gdp, on='Year')
    df_agg['Share'] = (df_agg['DataValue'] / df_agg['Total_GDP']) * 100

    # Sort categories to stack beautifully (Industrial bottom, then Res, then Com)
    cat_order = [
        'Industrial / Other',
        'Residential (Real Estate & Housing)',
        'Commercial (Offices, Retail, Services)'
    ]

    # Build the Plotly Wedge Plot (Stacked Area Chart)
    fig = go.Figure()
    colors = {
        'Commercial (Offices, Retail, Services)': '#1f77b4',  # Blue
        'Residential (Real Estate & Housing)': '#ff7f0e',     # Orange
        'Industrial / Other': '#7f7f7f'                     # Gray
    }

    for cat in cat_order:
        df_plot = df_agg[df_agg['Category'] == cat].sort_values('Year')
        fig.add_trace(go.Scatter(
            x=df_plot['Year'],
            y=df_plot['DataValue'],
            name=cat,
            mode='lines',
            line=dict(width=0.5, color=colors[cat]),
            stackgroup='one',  # This creates the stacked wedge effect
            fillcolor=colors[cat],
            hovertemplate=(
                f"<b>{cat}</b><br>"
                "Year: %{x}<br>"
                "Value Added: $%{y:,.0f} Billion<br>"
                "Share of GDP: %{customdata[0]:.1f}%<extra></extra>"
            ),
            customdata=df_plot[['Share']]
        ))

    fig.update_layout(
        title=(
            "GDP Contributions of Activities in Residential and Commercial Buildings<br>"
            "<sup>Source: BEA</sup>"
        ),
        xaxis_title="Year",
        yaxis_title="GDP Contribution ($ Billions)",
        template="plotly_white",
        hovermode="x unified",
        legend=dict(
            orientation="h",
            yanchor="top",
            y=-0.15,
            xanchor="center",
            x=0.5
        ),
        margin=dict(r=40, t=80, l=40, b=80),
        height=700
    )

    # Force x-axis to show integer years nicely
    fig.update_xaxes(dtick=2)

    html_path = f"{output_dir}/gdp_contributions.html"
    fig.write_html(html_path, default_width='100%', default_height='100%')
    print(f" -> Success! GDP wedge HTML saved to {html_path}")


# ==========================================
# 3. MAIN ORCHESTRATOR
# ==========================================

def main():
    """Main execution entry point."""
    print("=====================================================")
    print("  INITIALIZING PLOTTING PIPELINE")
    print("=====================================================\n")

    bls_key = None  # Insert your API key here
    eia_key = None  # Insert your API key here
    bea_key = None  # Insert your API key here
    census_key = None  # Insert your API key here
    # ita_key = None  # Insert your API key here

    missing_keys = []
    if not bls_key:
        missing_keys.append("BLS_API_KEY")
    if not eia_key:
        missing_keys.append("EIA_API_KEY")
    if not bea_key:
        missing_keys.append("BEA_API_KEY")
    if not census_key:
        missing_keys.append("CENSUS_API_KEY")
    # if not ita_key:
    #     missing_keys.append("ITA_API_KEY")

    if missing_keys:
        print("CRITICAL ERROR: The following API keys are missing:")
        for key in missing_keys:
            print(f" - {key}")
        print("Please add them before running this script.")
        return

    output_dir = "graphics"
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    try:
        eia_df = generate_eia_mapping_df()
        plot_energy_burden(output_dir)
        plot_fuel_price_ratio(eia_key, output_dir)
        plot_permits_construction(census_key, output_dir)
        plot_county_heating_equipment(census_key, output_dir)
        plot_ann_elec_sales(output_dir)
        plot_peak_data(output_dir)
        plot_utility_costs(eia_df, output_dir)
        plot_dsm_comprehensive_dashboard(2023, output_dir)
        plot_building_jobs_trend(bls_key, output_dir)
        plot_gdp_by_building_type(bea_key, output_dir)
        print(f"\nPipeline complete. Visuals saved to ./{output_dir}")
    except Exception as e:
        print(f"\nPIPELINE HALTED DUE TO ERROR: {e}")


if __name__ == "__main__":
    main()
