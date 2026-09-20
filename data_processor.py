import pandas as pd
import numpy as np

# Load and sort the data to ensure correct chronological returns
df = pd.read_csv("HSIR_event_data_long.csv")
df['date'] = pd.to_datetime(df['date'])
df = df.sort_values(by=['event_id', 'ticker', 't'])

# Calculate daily returns (R_i,t)
df['daily_return'] = df.groupby(['event_id', 'ticker'])['close'].pct_change()
df = df.dropna(subset=['daily_return'])

# Isolate the benchmark (market) returns
market_df = df[df['sector'] == 'Benchmark'][['event_id', 'date', 't', 'daily_return']]
market_df = market_df.rename(columns={'daily_return': 'market_return'})

# Isolate the stock returns and merge with market returns
stocks_df = df[df['sector'] != 'Benchmark'].copy()
merged_df = stocks_df.merge(market_df[['event_id', 't', 'market_return']], on=['event_id', 't'], how='inner')

processed_events = []

# Process each stock per event
for (event_id, ticker), group in merged_df.groupby(['event_id', 'ticker']):
    
    # 60-day Estimation Window (e.g., t = -70 to t = -11)
    estimation_window = group[group['t'] < -10]
    
    # 20-day Event Window (t = -10 to t = +10)
    event_window = group[(group['t'] >= -10) & (group['t'] <= 10)].copy()
    
    if not estimation_window.empty and not event_window.empty:
        # Calculate alpha and beta using linear regression (polyfit degree 1)
        beta, alpha = np.polyfit(estimation_window['market_return'], estimation_window['daily_return'], 1)
        
        # Calculate Expected Return, AR, and CAR for the event window
        event_window['expected_return'] = alpha + (beta * event_window['market_return'])
        event_window['AR'] = event_window['daily_return'] - event_window['expected_return']
        event_window['CAR'] = event_window['AR'].cumsum()
        
        processed_events.append(event_window)

# Combine all processed windows into a single DataFrame
processed_data = pd.concat(processed_events, ignore_index=True)

# Print a preview of the results
print(processed_data[['event_id', 't', 'ticker', 'daily_return', 'expected_return', 'AR', 'CAR']].head(15))

# Save the final calculated data
processed_data.to_csv("processed_data.csv", index=False)