import os
import pandas as pd

# ==============================================================================
# KONFIGURASI FILE DATA & FILTER TANGGAL
# ==============================================================================
DATA_PATHS = {
    "M5": r"C:\Users\Alief Akbar Purnama\Downloads\XAUUSDmM5-28jun18.csv",
    "M15": r"C:\Users\Alief Akbar Purnama\Downloads\XAUUSDmM15-28jun18.csv",
    "M30": r"C:\Users\Alief Akbar Purnama\Downloads\XAUUSDmM30-28jun18.csv",
    "H1": r"C:\Users\Alief Akbar Purnama\Downloads\XAUUSDmH1-28jun18.csv",
}

START_DATE = "2026-01-01 00:00:00"

def load_data(csv_path):
    kolom_mt5 = ['time', 'open', 'high', 'low', 'close', 'tick_volume', 'spread']
    try:
        df = pd.read_csv(csv_path, header=None, names=kolom_mt5, encoding="utf-16", sep=",")
        if df.shape[1] <= 1 or pd.isna(df['close']).all():
            df = pd.read_csv(csv_path, header=None, names=kolom_mt5, encoding="utf-8", sep=",")
        if df.shape[1] <= 1 or pd.isna(df['close']).all():
            df = pd.read_csv(csv_path, header=None, names=kolom_mt5, encoding="utf-16", sep="\t")
    except Exception:
        try:
            df = pd.read_csv(csv_path, header=None, names=kolom_mt5, encoding="utf-16", sep=",")
        except:
            df = pd.read_csv(csv_path, header=None, names=kolom_mt5, encoding="utf-8", sep=",")

    df["time"] = pd.to_datetime(df["time"])
    df = df.sort_values("time").reset_index(drop=True)
    return df

def inspect_all_data(start_date=START_DATE, save_filtered_csv=True):
    print("=" * 85)
    print(" " * 20 + f"PENGECEKAN DATA HISTORIS DARI: {start_date}")
    print("=" * 85)
    
    for tf_name, csv_path in DATA_PATHS.items():
        if not os.path.exists(csv_path):
            print(f"[!] File {csv_path} tidak ditemukan.")
            continue
            
        df = load_data(csv_path)
        total_rows = len(df)
        min_date_full = df['time'].min()
        max_date_full = df['time'].max()
        
        # Filter mulai dari 2026-01-01
        df_filtered = df[df["time"] >= start_date].copy().reset_index(drop=True)
        filtered_rows = len(df_filtered)
        
        print(f"\n>>> TIMEFRAME: {tf_name}")
        print(f"  * Rentang Total File : {min_date_full} s/d {max_date_full} ({total_rows:,} baris)")
        print(f"  * Terfilter >= {start_date[:10]} : {df_filtered['time'].min()} s/d {df_filtered['time'].max()} ({filtered_rows:,} baris candle)")
        
        if filtered_rows > 0:
            print("\n  [5 Baris Awal Periode 2026]:")
            print(df_filtered.head(5).to_string(index=False))
            print("\n  [5 Baris Terakhir / Terkini 2026]:")
            print(df_filtered.tail(5).to_string(index=False))
            
            # Opsi simpan data terfilter ke CSV terpisah
            if save_filtered_csv:
                output_name = f"XAUUSD_{tf_name}_2026_sekarang.csv"
                df_filtered.to_csv(output_name, index=False)
                print(f"\n  [+] File terfilter 2026 disimpan ke: {output_name}")
        else:
            print("  [!] Tidak ada data untuk periode tanggal tersebut.")
            
        print("-" * 85)

if __name__ == "__main__":
    inspect_all_data(start_date=START_DATE, save_filtered_csv=True)
