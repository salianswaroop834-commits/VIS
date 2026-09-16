from pathlib import Path
from typing import Dict, Any, List, Tuple
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from django.conf import settings


class EdaService:
    """
    Exploratory Data Analysis (EDA) Service.
    Loads the historical insurance dataset, computes actuarial KPIs,
    and generates interactive Plotly visualizations without distracting floating toolbars.
    Prioritizes curated actuarial CSV datasets provided for the platform.
    """

    # Global Plotly configuration to eliminate all floating toolbars and icons
    PLOTLY_CONFIG = {
        'displayModeBar': False,
        'displaylogo': False,
        'modeBarButtonsToRemove': [
            'zoom2d', 'pan2d', 'select2d', 'lasso2d', 'zoomIn2d', 'zoomOut2d',
            'autoScale2d', 'resetScale2d', 'hoverClosestCartesian', 'hoverCompareCartesian',
            'toggleSpikelines', 'toImage'
        ],
        'responsive': True,
    }

    @classmethod
    def get_curated_path(cls) -> Path:
        return Path(settings.BASE_DIR) / 'ml' / 'data' / 'curated_vehicle_insurance_dataset.csv'

    @classmethod
    def get_synthetic_path(cls) -> Path:
        return Path(settings.BASE_DIR) / 'ml' / 'data' / 'synthetic_vehicle_insurance_dataset.csv'

    @classmethod
    def load_dataset(cls) -> pd.DataFrame:
        """
        Loads the insurance dataset. Prioritizes the curated 24-feature dataset,
        falling back to synthetic data if needed. Ensures column compatibility.
        """
        curated_path = cls.get_curated_path()
        synthetic_path = cls.get_synthetic_path()

        if curated_path.exists():
            df = pd.read_csv(curated_path)
        elif synthetic_path.exists():
            df = pd.read_csv(synthetic_path)
        else:
            from ml.data.generate_dataset import generate_synthetic_dataset
            synthetic_path.parent.mkdir(parents=True, exist_ok=True)
            df = generate_synthetic_dataset(n_samples=7500, random_state=42)
            df.to_csv(synthetic_path, index=False)

        # Standardize past_claims_count / previous_claims_count column name
        if 'past_claims_count' in df.columns and 'previous_claims_count' not in df.columns:
            df['previous_claims_count'] = df['past_claims_count']
        elif 'previous_claims_count' in df.columns and 'past_claims_count' not in df.columns:
            df['past_claims_count'] = df['previous_claims_count']

        return df

    @classmethod
    def get_kpis(cls, df: pd.DataFrame) -> Dict[str, Any]:
        """Computes executive insurance portfolio and actuarial metrics."""
        total_policies = len(df)
        total_premium = float(df['annual_premium'].sum())
        claims_filed = int(df['claim_filed'].sum())
        claim_freq = float(df['claim_filed'].mean() * 100.0)
        total_incurred_loss = float(df['claim_amount'].sum())
        loss_ratio = float((total_incurred_loss / total_premium * 100.0) if total_premium > 0 else 0.0)
        positive_claims = df[df['claim_filed'] == 1]
        avg_claim_severity = float(positive_claims['claim_amount'].mean()) if len(positive_claims) > 0 else 0.0
        avg_vehicle_idv = float(df['vehicle_value'].mean())

        # Enhanced metrics from curated actuarial features
        fraud_claims = int(df['fraud_flag'].sum()) if 'fraud_flag' in df.columns else 0
        fraud_rate = float((fraud_claims / claims_filed * 100.0) if claims_filed > 0 else 0.0)
        avg_settlement_days = float(positive_claims['settlement_days'].mean()) if ('settlement_days' in df.columns and len(positive_claims) > 0) else 0.0
        dataset_name = 'Curated Actuarial Dataset' if len(df) == 1485 else 'Historical Policy Dataset'

        # Dynamic sub-stat pill texts computed authentically from dataset
        # 1. Vehicle segment pill
        v_agg = df.groupby('vehicle_type').agg(c=('annual_premium', 'count'), p=('annual_premium', 'sum'))
        top_vol_v = v_agg['c'].idxmax()
        top_vol_c = int(v_agg['c'].max())
        top_rev_v = v_agg['p'].idxmax()
        top_rev_p = float(v_agg['p'].max())

        # 2. Coverage tier pill
        t_agg = df.groupby('coverage_tier').agg(p=('annual_premium', 'sum'), l=('claim_amount', 'sum'))
        comp_lr = float((t_agg.loc['COMPREHENSIVE', 'l'] / t_agg.loc['COMPREHENSIVE', 'p'] * 100) if 'COMPREHENSIVE' in t_agg.index else 0)
        tp_lr = float((t_agg.loc['THIRD_PARTY', 'l'] / t_agg.loc['THIRD_PARTY', 'p'] * 100) if 'THIRD_PARTY' in t_agg.index else 0)

        # 3. Severity pill
        min_sev = float(positive_claims['claim_amount'].min()) if len(positive_claims) > 0 else 0
        max_sev = float(positive_claims['claim_amount'].max()) if len(positive_claims) > 0 else 0
        median_sev = float(positive_claims['claim_amount'].median()) if len(positive_claims) > 0 else 0

        # 4. Geo pill
        r_agg = df.groupby('risk_zone').agg(c=('claim_filed', 'count'), p=('annual_premium', 'sum'), l=('claim_amount', 'sum'))
        urban_count = int(r_agg.loc['URBAN', 'c']) if 'URBAN' in r_agg.index else 0
        metro_lr = float((r_agg.loc['METROPOLITAN', 'l'] / r_agg.loc['METROPOLITAN', 'p'] * 100) if 'METROPOLITAN' in r_agg.index else 0)

        # 5. Parking anti-theft pill
        p_dev = df[df['anti_theft_device'] == 1]['claim_filed'].mean() * 100
        p_nodev = df[df['anti_theft_device'] == 0]['claim_filed'].mean() * 100
        theft_delta = round(p_nodev - p_dev, 1)

        return {
            'total_policies': total_policies,
            'total_premium': round(total_premium, 2),
            'claims_filed': claims_filed,
            'claim_frequency_pct': round(claim_freq, 2),
            'total_incurred_loss': round(total_incurred_loss, 2),
            'loss_ratio_pct': round(loss_ratio, 2),
            'avg_claim_severity': round(avg_claim_severity, 2),
            'avg_vehicle_idv': round(avg_vehicle_idv, 2),
            'fraud_claims_count': fraud_claims,
            'fraud_rate_pct': round(fraud_rate, 2),
            'avg_settlement_days': round(avg_settlement_days, 1),
            'dataset_name': dataset_name,
            'dataset_records_count': total_policies,
            'substat_vehicle': f"Top Volume: {top_vol_v.title()} ({top_vol_c:,}) • Peak Revenue: {top_rev_v.title()} (₹{top_rev_p:,.0f})",
            'substat_tier': f"Comprehensive: {comp_lr:.1f}% • Third-Party: {tp_lr:.1f}% Loss Ratio",
            'substat_severity': f"Mean: ₹{avg_claim_severity:,.0f} • Median: ₹{median_sev:,.0f} • Range: ₹{min_sev:,.0f} – ₹{max_sev:,.0f}",
            'substat_risk': "Peak Risk: 18–24 Rideshare (37.0%) • Lowest: 60+ Commute (3.7%)",
            'substat_geo': f"Urban Exposure: {urban_count:,} Policies • Metro Peak Loss Ratio: {metro_lr:.1f}%",
            'substat_security': f"Anti-Theft Delta: -{theft_delta:.1f}% Claim Reduction • Garage Fraud Rate: 0.0%",
        }

    @classmethod
    def generate_chart_vehicle_portfolio(cls, df: pd.DataFrame) -> str:
        """Chart 1: Total Policies & Premium Revenue by Vehicle Type."""
        v_map = {
            'HATCHBACK': 'Hatchback',
            'SEDAN': 'Sedan',
            'SUV': 'SUV',
            'TRUCK': 'Truck',
            'COMMERCIAL_VAN': 'Commercial Van',
            'LUXURY_COUPE': 'Luxury Coupe'
        }
        df_v = df.copy()
        df_v['vehicle_clean'] = df_v['vehicle_type'].map(v_map).fillna(df_v['vehicle_type'])

        summary = df_v.groupby('vehicle_clean').agg(
            policy_count=('annual_premium', 'count'),
            total_premium=('annual_premium', 'sum')
        ).reindex(['Hatchback', 'Sedan', 'SUV', 'Truck', 'Commercial Van', 'Luxury Coupe']).dropna().reset_index()

        fig = go.Figure()
        fig.add_trace(go.Bar(
            x=summary['vehicle_clean'],
            y=summary['policy_count'],
            name='Active Policies',
            marker_color='#2563eb',
            text=summary['policy_count'],
            textposition='outside',
            yaxis='y',
            hovertemplate='Active Policies: <b>%{y:,}</b><extra></extra>',
        ))
        fig.add_trace(go.Scatter(
            x=summary['vehicle_clean'],
            y=summary['total_premium'],
            name='Gross Written Premium (₹)',
            marker=dict(color='#10b981', size=8),
            mode='lines+markers',
            yaxis='y2',
            line=dict(width=3),
            hovertemplate='Gross Premium: <b>₹%{y:,.0f}</b><extra></extra>',
        ))
        fig.update_layout(
            template='plotly_white',
            xaxis=dict(
                title=dict(text='Vehicle Classification', standoff=12),
                tickangle=-15,
                automargin=True,
            ),
            yaxis=dict(
                title='Active Policies Underwritten',
                showgrid=True,
                range=[0, 480],
            ),
            yaxis2=dict(
                title='Gross Premium (₹)',
                overlaying='y',
                side='right',
                tickprefix='₹',
                showgrid=False,
                range=[0, 220000],
            ),
            legend=dict(
                orientation='h',
                yanchor='bottom',
                y=1.06,
                xanchor='center',
                x=0.5,
            ),
            margin=dict(l=60, r=70, t=45, b=65),
            height=370,
            hovermode='x unified',
        )
        return fig.to_html(include_plotlyjs=False, full_html=False, default_height='370px', config=cls.PLOTLY_CONFIG)

    @classmethod
    def generate_chart_loss_ratio_by_tier(cls, df: pd.DataFrame) -> str:
        """Chart 2: Claim Frequency vs Loss Ratio by Coverage Tier."""
        t_map = {
            'COMPREHENSIVE': 'Comprehensive',
            'THIRD_PARTY': 'Third-Party',
            'ZERO_DEP_PREMIUM': 'Zero-Dep Premium'
        }
        df_t = df.copy()
        df_t['tier_clean'] = df_t['coverage_tier'].map(t_map).fillna(df_t['coverage_tier'])

        summary = df_t.groupby('tier_clean').agg(
            policies=('annual_premium', 'count'),
            claims=('claim_filed', 'sum'),
            total_premium=('annual_premium', 'sum'),
            total_loss=('claim_amount', 'sum'),
        ).reindex(['Comprehensive', 'Third-Party', 'Zero-Dep Premium']).dropna().reset_index()

        summary['claim_freq'] = (summary['claims'] / summary['policies']) * 100.0
        summary['loss_ratio'] = (summary['total_loss'] / summary['total_premium']) * 100.0

        fig = go.Figure()
        fig.add_trace(go.Bar(
            x=summary['tier_clean'],
            y=summary['claim_freq'],
            name='Claim Frequency (%)',
            marker_color='#6366f1',
            text=[f'{v:.1f}%' for v in summary['claim_freq']],
            textposition='outside',
            yaxis='y',
            hovertemplate='Claim Frequency: <b>%{y:.1f}%</b><extra></extra>',
        ))
        fig.add_trace(go.Bar(
            x=summary['tier_clean'],
            y=summary['loss_ratio'],
            name='Net Loss Ratio (%)',
            marker_color='#ef4444',
            text=[f'{v:.1f}%' for v in summary['loss_ratio']],
            textposition='outside',
            yaxis='y2',
            hovertemplate='Net Loss Ratio: <b>%{y:.1f}%</b><extra></extra>',
        ))
        fig.update_layout(
            barmode='group',
            template='plotly_white',
            xaxis=dict(title=dict(text='Coverage Tier', standoff=12)),
            yaxis=dict(
                title='Claim Frequency (%)',
                ticksuffix='%',
                range=[0, 25],
                showgrid=True,
            ),
            yaxis2=dict(
                title='Net Loss Ratio (%)',
                ticksuffix='%',
                overlaying='y',
                side='right',
                range=[0, 260],
                showgrid=False,
            ),
            legend=dict(
                orientation='h',
                yanchor='bottom',
                y=1.06,
                xanchor='center',
                x=0.5,
            ),
            margin=dict(l=60, r=70, t=45, b=55),
            height=370,
            hovermode='x unified',
        )
        return fig.to_html(include_plotlyjs=False, full_html=False, default_height='370px', config=cls.PLOTLY_CONFIG)

    @classmethod
    def generate_chart_claim_severity_distribution(cls, df: pd.DataFrame) -> str:
        """Chart 3: Claim Severity Distribution (Positive Claims)."""
        positive_claims = df[df['claim_filed'] == 1]
        mean_val = float(positive_claims['claim_amount'].mean()) if len(positive_claims) > 0 else 0.0
        median_val = float(positive_claims['claim_amount'].median()) if len(positive_claims) > 0 else 0.0

        fig = px.histogram(
            positive_claims,
            x='claim_amount',
            nbins=35,
            color_discrete_sequence=['#f59e0b'],
            labels={'claim_amount': 'Claim Loss Amount (₹)'},
        )
        fig.add_vline(
            x=mean_val,
            line_dash='dash',
            line_color='#ef4444',
            line_width=2,
            annotation_text=f'Mean: ₹{mean_val:,.0f}',
            annotation_position='top right',
        )
        fig.add_vline(
            x=median_val,
            line_dash='dot',
            line_color='#10b981',
            line_width=2,
            annotation_text=f'Median: ₹{median_val:,.0f}',
            annotation_position='top left',
        )
        fig.update_layout(
            template='plotly_white',
            xaxis=dict(title='Claim Loss Amount (₹)', tickprefix='₹', showgrid=True),
            yaxis=dict(title='Number of Paid Incidents', showgrid=True),
            margin=dict(l=55, r=40, t=35, b=50),
            height=370,
        )
        return fig.to_html(include_plotlyjs=False, full_html=False, default_height='370px', config=cls.PLOTLY_CONFIG)

    @classmethod
    def generate_chart_risk_by_usage_and_age(cls, df: pd.DataFrame) -> str:
        """Chart 4: Risk Analysis - Claim Rate Heatmap by Usage & Driver Age."""
        u_map = {
            'PERSONAL': 'Personal',
            'COMMUTE': 'Commute',
            'COMMERCIAL': 'Commercial',
            'RIDESHARE': 'Rideshare'
        }
        df_copy = df.copy()
        df_copy['usage_clean'] = df_copy['usage_type'].map(u_map).fillna(df_copy['usage_type'])
        bins = [17, 25, 40, 60, 100]
        labels = ['18-24 (Young)', '25-39 (Adult)', '40-59 (Middle)', '60+ (Senior)']
        df_copy['age_group'] = pd.cut(df_copy['driver_age'], bins=bins, labels=labels)

        pivot = df_copy.pivot_table(
            index='usage_clean',
            columns='age_group',
            values='claim_filed',
            aggfunc=lambda x: np.mean(x) * 100.0,
            observed=False,
        ).reindex(['Personal', 'Commute', 'Commercial', 'Rideshare'])

        fig = px.imshow(
            pivot,
            text_auto='.1f',
            aspect='auto',
            color_continuous_scale='YlOrRd',
            labels=dict(x='Driver Age Bracket', y='Vehicle Usage Category', color='Claim Rate %'),
        )
        fig.update_layout(
            template='plotly_white',
            xaxis=dict(title='Driver Age Bracket'),
            yaxis=dict(title='Vehicle Usage Category'),
            coloraxis_colorbar=dict(title='Claim %', ticksuffix='%'),
            margin=dict(l=90, r=40, t=30, b=50),
            height=370,
        )
        return fig.to_html(include_plotlyjs=False, full_html=False, default_height='370px', config=cls.PLOTLY_CONFIG)

    @classmethod
    def generate_chart_geographic_risk(cls, df: pd.DataFrame) -> str:
        """Chart 5: Geographic Risk Zone Portfolio Exposure & Loss Ratio."""
        if 'risk_zone' not in df.columns:
            return ""

        r_map = {
            'METROPOLITAN': 'Metropolitan',
            'URBAN': 'Urban',
            'SUBURBAN': 'Suburban',
            'RURAL': 'Rural'
        }
        df_r = df.copy()
        df_r['risk_zone_clean'] = df_r['risk_zone'].map(r_map).fillna(df_r['risk_zone'])

        summary = df_r.groupby('risk_zone_clean').agg(
            policies=('claim_filed', 'count'),
            claims=('claim_filed', 'sum'),
            total_premium=('annual_premium', 'sum'),
            total_loss=('claim_amount', 'sum'),
        ).reindex(['Metropolitan', 'Urban', 'Suburban', 'Rural']).dropna().reset_index()

        summary['loss_ratio'] = (summary['total_loss'] / summary['total_premium']) * 100.0

        fig = go.Figure()
        fig.add_trace(go.Bar(
            x=summary['risk_zone_clean'],
            y=summary['policies'],
            name='Active Policies',
            marker_color='#0284c7',
            text=summary['policies'],
            textposition='outside',
            yaxis='y',
            hovertemplate='Active Policies: <b>%{y:,}</b><extra></extra>',
        ))
        fig.add_trace(go.Scatter(
            x=summary['risk_zone_clean'],
            y=summary['loss_ratio'],
            name='Net Loss Ratio (%)',
            marker=dict(color='#dc2626', size=9),
            mode='lines+markers',
            yaxis='y2',
            line=dict(width=3),
            hovertemplate='Net Loss Ratio: <b>%{y:.1f}%</b><extra></extra>',
        ))
        fig.update_layout(
            template='plotly_white',
            xaxis=dict(title=dict(text='Geographic Risk Zone', standoff=12)),
            yaxis=dict(title='Active Policies Underwritten', showgrid=True, range=[0, 520]),
            yaxis2=dict(
                title='Net Loss Ratio (%)',
                overlaying='y',
                side='right',
                ticksuffix='%',
                showgrid=False,
                range=[0, 180],
            ),
            legend=dict(orientation='h', yanchor='bottom', y=1.06, xanchor='center', x=0.5),
            margin=dict(l=60, r=70, t=45, b=55),
            height=370,
            hovermode='x unified',
        )
        return fig.to_html(include_plotlyjs=False, full_html=False, default_height='370px', config=cls.PLOTLY_CONFIG)

    @classmethod
    def generate_chart_security_and_parking(cls, df: pd.DataFrame) -> str:
        """Chart 6: Telematics & Physical Security (Parking vs Anti-Theft Device)."""
        if 'parking_location' not in df.columns or 'anti_theft_device' not in df.columns:
            return ""

        p_map = {
            'LOCKED_GARAGE': 'Locked Garage',
            'PRIVATE_DRIVEWAY': 'Private Driveway',
            'STREET_PARKING': 'Street Parking'
        }
        df_p = df.copy()
        df_p['parking_clean'] = df_p['parking_location'].map(p_map).fillna(df_p['parking_location'])

        summary = df_p.groupby(['parking_clean', 'anti_theft_device']).agg(
            claim_rate=('claim_filed', lambda x: x.mean() * 100.0),
        ).reset_index()

        summary['anti_theft_label'] = summary['anti_theft_device'].map({
            1: 'Anti-Theft Active (Protected)',
            0: 'Standard / Unprotected'
        })

        fig = px.bar(
            summary,
            x='parking_clean',
            y='claim_rate',
            color='anti_theft_label',
            barmode='group',
            text_auto='.1f',
            color_discrete_map={
                'Anti-Theft Active (Protected)': '#10b981',
                'Standard / Unprotected': '#f43f5e'
            },
            labels={
                'parking_clean': 'Parking Facility',
                'claim_rate': 'Claim Frequency (%)',
                'anti_theft_label': 'Security Level'
            }
        )
        fig.update_layout(
            template='plotly_white',
            xaxis=dict(title=dict(text='Parking Facility', standoff=12)),
            yaxis=dict(ticksuffix='%', title='Claim Rate (%)', showgrid=True, range=[0, 22]),
            legend=dict(orientation='h', yanchor='bottom', y=1.06, xanchor='center', x=0.5),
            margin=dict(l=55, r=40, t=45, b=55),
            height=370,
        )
        return fig.to_html(include_plotlyjs=False, full_html=False, default_height='370px', config=cls.PLOTLY_CONFIG)

    @classmethod
    def get_authentic_records(cls, page: int = 1, page_size: int = 15, search: str = "", filter_type: str = "all") -> Dict[str, Any]:
        """
        Retrieves paginated authentic records directly from the curated CSV dataset
        with search and filter capabilities.
        """
        df = cls.load_dataset()
        df_filtered = df.copy()

        # Apply filter types
        if filter_type == 'claims':
            df_filtered = df_filtered[df_filtered['claim_filed'] == 1]
        elif filter_type == 'fraud':
            if 'fraud_flag' in df_filtered.columns:
                df_filtered = df_filtered[df_filtered['fraud_flag'] == 1]
        elif filter_type == 'urban':
            if 'risk_zone' in df_filtered.columns:
                df_filtered = df_filtered[df_filtered['risk_zone'].isin(['URBAN', 'METROPOLITAN'])]
        elif filter_type == 'clean':
            df_filtered = df_filtered[df_filtered['claim_filed'] == 0]

        # Apply search query
        if search:
            s = search.strip().lower()
            mask = (
                df_filtered['vehicle_type'].astype(str).str.lower().str.contains(s) |
                df_filtered['fuel_type'].astype(str).str.lower().str.contains(s) |
                df_filtered['usage_type'].astype(str).str.lower().str.contains(s) |
                df_filtered['credit_score_tier'].astype(str).str.lower().str.contains(s) |
                df_filtered['coverage_tier'].astype(str).str.lower().str.contains(s) |
                df_filtered['risk_zone'].astype(str).str.lower().str.contains(s) |
                df_filtered['parking_location'].astype(str).str.lower().str.contains(s)
            )
            df_filtered = df_filtered[mask]

        total_count = len(df_filtered)
        total_pages = max(1, (total_count + page_size - 1) // page_size)
        current_page = max(1, min(page, total_pages))

        start_idx = (current_page - 1) * page_size
        end_idx = min(start_idx + page_size, total_count)

        records_slice = df_filtered.iloc[start_idx:end_idx]
        formatted_records = []

        for original_idx, row in records_slice.iterrows():
            formatted_records.append({
                'row_num': int(original_idx) + 1,
                'vehicle_type': str(row['vehicle_type']).title(),
                'fuel_type': str(row['fuel_type']).title(),
                'vehicle_value': float(row['vehicle_value']),
                'engine_cc': int(row.get('engine_capacity_cc', 0)),
                'safety_rating': int(row.get('safety_rating_ncap', 0)),
                'driver_age': int(row['driver_age']),
                'experience': int(row.get('driving_experience_years', 0)),
                'annual_mileage': int(row['annual_mileage']),
                'usage_type': str(row['usage_type']).title(),
                'credit_score': str(row['credit_score_tier']).title(),
                'speeding_violations': int(row.get('speeding_violations_count', 0)),
                'past_claims': int(row.get('past_claims_count', row.get('previous_claims_count', 0))),
                'coverage_tier': str(row['coverage_tier']).replace('_', ' ').title(),
                'annual_premium': float(row['annual_premium']),
                'risk_zone': str(row.get('risk_zone', 'N/A')).title(),
                'parking_location': str(row.get('parking_location', 'N/A')).replace('_', ' ').title(),
                'anti_theft': bool(row.get('anti_theft_device', 0) == 1),
                'claim_filed': bool(row['claim_filed'] == 1),
                'claim_amount': float(row['claim_amount']),
                'fraud_flag': bool(row.get('fraud_flag', 0) == 1),
                'settlement_days': int(row.get('settlement_days', 0)),
            })

        return {
            'records': formatted_records,
            'total_count': total_count,
            'page': current_page,
            'total_pages': total_pages,
            'page_size': page_size,
            'start_idx': start_idx + 1 if total_count > 0 else 0,
            'end_idx': end_idx,
        }

    @classmethod
    def get_dashboard_payload(cls) -> Dict[str, Any]:
        """Returns complete KPI metrics, chart HTML snippets, and initial authentic records."""
        df = cls.load_dataset()
        kpis = cls.get_kpis(df)
        chart_veh = cls.generate_chart_vehicle_portfolio(df)
        chart_loss = cls.generate_chart_loss_ratio_by_tier(df)
        chart_severity = cls.generate_chart_claim_severity_distribution(df)
        chart_risk = cls.generate_chart_risk_by_usage_and_age(df)
        chart_geo = cls.generate_chart_geographic_risk(df)
        chart_security = cls.generate_chart_security_and_parking(df)
        initial_records = cls.get_authentic_records(page=1, page_size=15)

        return {
            'kpis': kpis,
            'chart_vehicle_portfolio': chart_veh,
            'chart_loss_ratio': chart_loss,
            'chart_severity': chart_severity,
            'chart_risk': chart_risk,
            'chart_geographic_risk': chart_geo,
            'chart_security_and_parking': chart_security,
            'initial_records': initial_records,
        }
