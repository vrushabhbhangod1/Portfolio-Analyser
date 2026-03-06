"""
Timeline Module - Multi-period portfolio analysis
Handles date range detection, aggregation, and overlap calculation
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Tuple
from collections import defaultdict


def detect_date_ranges(statements: List[Dict]) -> Dict:
    """
    Analyze all statements and detect date ranges
    
    KEY: Each broker may have multiple monthly statements.
    We need to find:
    - Each broker's full date range (earliest start to latest end)
    - The overlap period where ALL brokers have data
    
    Example:
    E*TRADE: Jan, Feb, Mar → Range: Jan 1 - Mar 31
    Fidelity: Jan, Feb → Range: Jan 1 - Feb 28
    IBKR: Feb, Mar → Range: Feb 1 - Mar 31
    Overlap: Feb only (the only month ALL three have)
    
    Returns:
    - min_date: Earliest date across ALL statements
    - max_date: Latest date across ALL statements
    - overlap_start: Start of period where ALL brokers have data
    - overlap_end: End of period where ALL brokers have data
    - broker_ranges: Dict of date ranges per broker
    """
    
    if not statements:
        return None
    
    # Group by broker to find each broker's range
    broker_ranges = defaultdict(lambda: {'start': None, 'end': None, 'periods': []})
    
    # Collect date ranges per account (broker + account_number label)
    for stmt in statements:
        broker = stmt['broker']
        acct = stmt.get('account_number')
        label = f"{broker} ({acct})" if acct else broker
        start = stmt['start_date']
        end = stmt['end_date']

        if not start or not end:
            continue

        # Update account's min/max dates
        if broker_ranges[label]['start'] is None or start < broker_ranges[label]['start']:
            broker_ranges[label]['start'] = start
        if broker_ranges[label]['end'] is None or end > broker_ranges[label]['end']:
            broker_ranges[label]['end'] = end

        broker_ranges[label]['periods'].append({'start': start, 'end': end})
    
    # Find global min and max
    all_starts = [r['start'] for r in broker_ranges.values() if r['start']]
    all_ends = [r['end'] for r in broker_ranges.values() if r['end']]
    
    if not all_starts or not all_ends:
        return {
            'min_date': None,
            'max_date': None,
            'overlap_start': None,
            'overlap_end': None,
            'has_overlap': False,
            'broker_ranges': dict(broker_ranges),
            'total_months': 0,
            'overlap_months': 0
        }
    
    min_date = min(all_starts)
    max_date = max(all_ends)
    
    # Find overlap (where ALL brokers have data)
    # Overlap start = latest start date (when the last broker starts)
    # Overlap end = earliest end date (when the first broker ends)
    overlap_start = max(all_starts)  # Latest start date
    overlap_end = min(all_ends)      # Earliest end date
    
    # Check if there's actually an overlap
    has_overlap = overlap_start <= overlap_end
    
    result = {
        'min_date': min_date,
        'max_date': max_date,
        'overlap_start': overlap_start if has_overlap else None,
        'overlap_end': overlap_end if has_overlap else None,
        'has_overlap': has_overlap,
        'broker_ranges': dict(broker_ranges),
        'total_months': calculate_months_between(min_date, max_date),
        'overlap_months': calculate_months_between(overlap_start, overlap_end) if has_overlap else 0
    }
    
    return result


def calculate_months_between(start: datetime, end: datetime) -> int:
    """Calculate number of months between two dates"""
    if not start or not end:
        return 0
    
    months = (end.year - start.year) * 12 + (end.month - start.month) + 1
    return max(0, months)


def generate_month_range(start: datetime, end: datetime) -> List[str]:
    """
    Generate list of YYYY-MM strings between start and end dates
    
    Example: 2025-01 to 2025-03 -> ['2025-01', '2025-02', '2025-03']
    """
    months = []
    current = start.replace(day=1)
    end_month = end.replace(day=1)
    
    while current <= end_month:
        months.append(current.strftime('%Y-%m'))
        # Move to next month
        if current.month == 12:
            current = current.replace(year=current.year + 1, month=1)
        else:
            current = current.replace(month=current.month + 1)
    
    return months


def aggregate_by_month(statements: List[Dict]) -> Dict[str, Dict]:
    """
    Aggregate statements by month
    
    Key insight: Each statement is ONE month from ONE broker.
    We aggregate all months together, grouping by YYYY-MM.
    
    Returns dict with structure:
    {
      '2025-01': {
        'brokers': ['E*TRADE', 'IBKR'],
        'data': {
          'E*TRADE': {...E*TRADE Jan statement...},
          'IBKR': {...IBKR Jan statement...}
        },
        'total_value': 150000,
        ...
      },
      '2025-02': {
        'brokers': ['E*TRADE', 'Fidelity', 'IBKR'],
        'data': {
          'E*TRADE': {...E*TRADE Feb statement...},
          'Fidelity': {...Fidelity Feb statement...},
          'IBKR': {...IBKR Feb statement...}
        },
        ...
      }
    }
    """
    
    monthly_data = defaultdict(lambda: {
        'brokers': set(),
        'data': {},
        'total_start_value': 0,
        'total_end_value': 0,
        'total_deposits': 0,
        'total_withdrawals': 0,
        'total_realised_gains': 0,
        'total_unrealised_gains': 0
    })
    
    for stmt in statements:
        broker = stmt['broker']
        start = stmt['start_date']
        end = stmt['end_date']
        
        # Skip statements without valid dates
        if not start or not end:
            continue
        
        # Generate month key (YYYY-MM of end date)
        # Each monthly statement represents that month
        month_key = end.strftime('%Y-%m')
        
        # Store this broker's data for this month
        monthly_data[month_key]['brokers'].add(broker)
        monthly_data[month_key]['data'][broker] = stmt
        
        # Add to monthly totals (sum across all brokers in this month)
        monthly_data[month_key]['total_start_value'] += stmt['starting_value']
        monthly_data[month_key]['total_end_value'] += stmt['ending_value']
        monthly_data[month_key]['total_deposits'] += stmt['deposits']
        monthly_data[month_key]['total_withdrawals'] += stmt['withdrawals']
        monthly_data[month_key]['total_realised_gains'] += stmt['realised_gains']
        monthly_data[month_key]['total_unrealised_gains'] += stmt['unrealised_gains']
    
    # Convert sets to lists and calculate returns
    for month_key, data in monthly_data.items():
        data['brokers'] = sorted(list(data['brokers']))
        
        # Calculate monthly return
        if data['total_start_value'] > 0:
            net_cash_flow = data['total_deposits'] - data['total_withdrawals']
            # TWR = (End - Cash Flow) / Start - 1
            data['return'] = ((data['total_end_value'] - net_cash_flow) / data['total_start_value'] - 1) * 100
        else:
            data['return'] = 0
        
        data['net_cash_flow'] = data['total_deposits'] - data['total_withdrawals']
    
    return dict(monthly_data)


def aggregate_by_year(statements: List[Dict]) -> Dict[str, Dict]:
    """
    Aggregate statements by calendar year
    
    Returns dict with structure:
    {
      '2025': {
        'brokers': ['E*TRADE', 'IBKR'],
        'months': ['2025-01', '2025-02', ...],
        'start_value': 100000,
        'end_value': 130000,
        'total_return': 30.0,
        'ytd': True/False (whether full year or YTD)
      }
    }
    """
    
    # First get monthly data
    monthly_data = aggregate_by_month(statements)
    
    # If no monthly data, return empty dict
    if not monthly_data:
        return {}
    
    yearly_data = defaultdict(lambda: {
        'brokers': set(),
        'months': [],
        'start_value': 0,
        'end_value': 0,
        'total_deposits': 0,
        'total_withdrawals': 0,
        'total_realised_gains': 0,
        'total_unrealised_gains': 0,
        'monthly_returns': []
    })
    
    # Sort months
    sorted_months = sorted(monthly_data.keys())
    
    for month_key in sorted_months:
        year = month_key[:4]  # '2025-01' -> '2025'
        month_data = monthly_data[month_key]
        
        yearly_data[year]['brokers'].update(month_data['brokers'])
        yearly_data[year]['months'].append(month_key)
        yearly_data[year]['total_deposits'] += month_data['total_deposits']
        yearly_data[year]['total_withdrawals'] += month_data['total_withdrawals']
        yearly_data[year]['total_realised_gains'] += month_data['total_realised_gains']
        yearly_data[year]['total_unrealised_gains'] += month_data['total_unrealised_gains']
        yearly_data[year]['monthly_returns'].append(month_data['return'])
    
    # Calculate year values and returns
    for year, data in yearly_data.items():
        data['brokers'] = sorted(list(data['brokers']))
        
        # Get first and last month data
        first_month = data['months'][0]
        last_month = data['months'][-1]
        
        data['start_value'] = monthly_data[first_month]['total_start_value']
        data['end_value'] = monthly_data[last_month]['total_end_value']
        data['net_cash_flow'] = data['total_deposits'] - data['total_withdrawals']
        
        # Calculate annual return
        if data['start_value'] > 0:
            data['total_return'] = ((data['end_value'] - data['net_cash_flow']) / data['start_value'] - 1) * 100
        else:
            data['total_return'] = 0
        
        # Check if full year (Jan-Dec) or YTD
        data['is_full_year'] = (len(data['months']) == 12 and 
                                data['months'][0].endswith('-01') and 
                                data['months'][-1].endswith('-12'))
        data['ytd'] = not data['is_full_year']
    
    return dict(yearly_data)


def filter_to_overlap(monthly_data: Dict, overlap_start: datetime, overlap_end: datetime) -> Dict:
    """
    Filter monthly data to only include overlapping period
    """
    
    if not overlap_start or not overlap_end:
        return {}
    
    overlap_months = generate_month_range(overlap_start, overlap_end)
    
    filtered = {
        month: data 
        for month, data in monthly_data.items() 
        if month in overlap_months
    }
    
    return filtered


def create_timeline_dataframe(monthly_data: Dict) -> pd.DataFrame:
    """
    Create a pandas DataFrame from monthly data for easy charting
    
    Columns: month, date, value, return, deposits, withdrawals, brokers_count
    """
    
    rows = []
    
    for month_key in sorted(monthly_data.keys()):
        data = monthly_data[month_key]
        
        rows.append({
            'month': month_key,
            'date': datetime.strptime(month_key, '%Y-%m'),
            'start_value': data['total_start_value'],
            'end_value': data['total_end_value'],
            'return_pct': data['return'],
            'deposits': data['total_deposits'],
            'withdrawals': data['total_withdrawals'],
            'net_cash_flow': data['net_cash_flow'],
            'realised_gains': data['total_realised_gains'],
            'unrealised_gains': data['total_unrealised_gains'],
            'brokers': ', '.join(data['brokers']),
            'brokers_count': len(data['brokers'])
        })
    
    df = pd.DataFrame(rows)
    
    if not df.empty:
        df = df.sort_values('date')
    
    return df


def calculate_cumulative_returns(df: pd.DataFrame) -> pd.DataFrame:
    """
    Add cumulative return column to timeline dataframe
    Starting at 100, showing relative performance
    """
    
    if df.empty:
        return df
    
    df = df.copy()
    
    # Calculate cumulative returns (starting at 100)
    df['cumulative_value'] = 100.0
    
    for i in range(len(df)):
        if i == 0:
            df.loc[df.index[i], 'cumulative_value'] = 100.0
        else:
            prev_value = df.loc[df.index[i-1], 'cumulative_value']
            monthly_return = df.loc[df.index[i], 'return_pct'] / 100
            df.loc[df.index[i], 'cumulative_value'] = prev_value * (1 + monthly_return)
    
    return df


def get_broker_timeline(statements: List[Dict], broker: str) -> pd.DataFrame:
    """
    Get timeline for a specific broker (full date range)
    """
    
    # Filter statements for this broker
    broker_statements = [s for s in statements if s['broker'] == broker]
    
    if not broker_statements:
        return pd.DataFrame()
    
    # Aggregate by month
    monthly_data = aggregate_by_month(broker_statements)
    
    # Create dataframe
    df = create_timeline_dataframe(monthly_data)
    df = calculate_cumulative_returns(df)
    
    return df
