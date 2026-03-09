import math
from pprint import pprint
import re
from langchain_openai import ChatOpenAI
from langchain_core.documents import Document
from langchain_ollama import OllamaLLM
import pandas as pd
import categorize
from utils import load_pdf, export_to_csv, check_categorized_data, all_pdfs_in_folder, all_csvs_in_folder, load_pdf_as_dataframes, read_csv, count_categories, fmt_sankeymatic
from boa import categorize_boa, extract_boa_transactions
from schwab import categorize_schwab, extract_schwab_transactions
from barclays import categorize_barclays, extract_barclays_transactions
from paypal import categorize_paypal, extract_paypal_transactions
from dotenv import load_dotenv
# Load environment variables from .env file
load_dotenv()


# Fast & brittle categorization using a regex process
def categorize_pdf_to_csv_v1(pdf_path: str, extract_documents: callable, categorize: callable, model: OllamaLLM) -> None:
    documents: list[Document] = load_pdf(pdf_path)
    transactions = extract_documents(documents)
    # print(f'Extracted {len(transactions)} transactions')
    categorized_data = categorize(model, transactions)
    check_categorized_data(categorized_data)
    output_csv = pdf_path.replace(".pdf", "_categorized.csv").replace(".PDF", "_categorized.csv")
    export_to_csv(categorized_data, output_csv)

# Slower but more accurate categorization using docling
def categorize_pdf_to_csv_v2(pdf_path: str, extract_dataframes: callable, categorize: callable, model: OllamaLLM) -> None:
    dataframes = load_pdf_as_dataframes(pdf_path)
    # print(f'Extracted {len(dataframes)} dataframes')
    transactions = extract_dataframes(dataframes, pdf_path)
    # print(f'Extracted {len(transactions)} transactions from dataframes')
    categorized_data = categorize(model, transactions)
    check_categorized_data(categorized_data)
    output_csv = pdf_path.replace(".pdf", "_categorized.csv").replace(".PDF", "_categorized.csv")
    export_to_csv(categorized_data, output_csv)


def get_possible_column(cols: pd.Index, colname: str) -> int | None:
    try:
        index = cols.get_loc(colname)
        if type(index) == int:
            return index
        # fall back to fuzzy match
        pattern = re.compile(colname)
        matching_cols = [col for col in cols if pattern.search(col)]
        if len(matching_cols) >= 1:
            return cols.get_loc(matching_cols[0])
            # return first match
        return None
    except KeyError:
        return None

def description_column_index(df: pd.DataFrame) -> int | None:
    index = get_possible_column(df.columns, "Description")
    if index == None:
        index = get_possible_column(df.columns, "Transactions.Description")
    if index == None:
        index = get_possible_column(df.columns, "Schwab Bank Investor Checking TM (continued).Activity (continued).Description")
    if index == None:
        index = get_possible_column(df.columns, "Activity (continued).Description")
    if index == None:
        index = get_possible_column(df.columns, "Schwab Bank Investor Checking TM (continued).Activity (continued).Description")
    if index == None:
        index = get_possible_column(df.columns, "Description.Interest Charged")
    return index


def date_column_index(df: pd.DataFrame) -> int | None:
    index = get_possible_column(df.columns, "Date Posted")
    if index == None:
        index = get_possible_column(df.columns, "Activity Posted")
    if index == None:
        index = get_possible_column(df.columns, "Activity Date Posted")
    if index == None:
        index = get_possible_column(df.columns, "Schwab Bank Investor Checking TM.Activity.Date Posted")
    if index == None:
        index = get_possible_column(df.columns, "Activity (continued).Date Posted")
    if index == None:
        index = get_possible_column(df.columns, "Schwab Bank Investor Checking TM (continued).Activity (continued).Date Posted")
    if index == None:
        index = get_possible_column(df.columns, "Transaction Date")
    if index == None:
        index = get_possible_column(df.columns, "Transactions.Transaction Date")
    if index == None:
        index = get_possible_column(df.columns, "Transaction Date.")
    return index
    

def amount_column_index(df: pd.DataFrame) -> int | None:
    index = get_possible_column(df.columns, "Debits")
    if index == None:
        index = get_possible_column(df.columns, "Credits")
    if index == None:
        index = get_possible_column(df.columns, "Account Number: 440018794451.Activity (continued).Credits")
    if index == None:
        index = get_possible_column(df.columns, "Amount")
    if index == None:
        index = get_possible_column(df.columns, "Amount.")
    if index == None:
        index = get_possible_column(df.columns, "Transactions.Amount")
    return index

def columns_for_df(df) -> list[int]:
    date_idx = date_column_index(df)
    desc_idx = description_column_index(df)
    amount_idx = amount_column_index(df)
    return [date_idx, desc_idx, amount_idx]

def is_valid_df(cols: list[int]) -> bool: 
    return len(cols) == 3 and cols[0] is not None and cols[1] is not None and cols[2] is not None

def invalid_float(s):
    try:
        float(s)
        return False
    except ValueError:
        return True

def parse_money(s):
    # Remove $ and commas, keep negative sign if present
    cleaned = re.sub(r'[^\d.-]', '', s)
    if invalid_float(cleaned):
        return math.nan
    return float(cleaned)


def convert_dfs(df: pd.DataFrame, cols: list[int]) -> list[list[str]]:
    to_return = []
    credits_idx = get_possible_column(df.columns, "Credits")

    for index, row in df.iterrows():
        try:
            date = row.iloc[cols[0]]
            desc = row.iloc[cols[1]]
            orig_amt = row.iloc[cols[2]]
            if credits_idx is not None and row.iloc[credits_idx] is not None and row.iloc[credits_idx] != "":
                orig_amt = row.iloc[credits_idx]
            amt = math.nan
            # print(f'Extracted {date}:{desc}:{orig_amt}')
            if type(orig_amt) == str:
                amt = parse_money(orig_amt)
            if math.isnan(amt):
                # print(f"bad amt {orig_amt}")
                continue
            if date is None or date == "":
                # print(f"empty date: skipping")
                continue
            if desc is None or desc == "":
                # print(f"empty description: skipping")
                continue
            to_return.append([date, desc, amt])
        except IndexError:
            print(f"bad row {row}")
            continue
    return to_return

def extract_dataframes(dataframes: list[pd.DataFrame], origin: str) -> list[str]:
    valid_dataframes = []
    for df in dataframes:
        cols = columns_for_df(df)
        if is_valid_df(cols):
            # print(f'Valid dataframe {cols}')
            rows = convert_dfs(df, cols)
            valid_dataframes.extend(rows)
        else:
            print(f'Skipping invalid dataframe in file:{origin} \n{", ".join(str(c) for c in df.columns)}\n')
    # print(f'Extracted {len(valid_dataframes)} transactions from dataframes')
    return valid_dataframes

def categorize_all_pdfs_in_folder(pdf_folder: str, pdf_to_csv: callable):
    print(f'\nReading folder {pdf_folder}\n')
    pdfs = all_pdfs_in_folder(pdf_folder)
    for pdf_file in pdfs:
        pdf_to_csv(pdf_file)

models = {
    "gemma2:27b": OllamaLLM(model="gemma2:27b", temperature=0.0, request_timeout=60), # Most accurate free model. Not very fast.
    "gpt-4": ChatOpenAI(model="gpt-4", temperature=0.0, request_timeout=60), # Works best, but slow & most expensive.
    "gpt-4o-mini": ChatOpenAI(model="gpt-4o-mini", temperature=0.0, request_timeout=60), # Works slightly faster than gpt-4, less accurate, still costs money
}

# Main function
def main():
    # Models. TODO: parameterize this
    model = models["gemma2:27b"]
    # First categorize all PDFs
    # Most LLMs are not really good at directly reading PDFs. We have to extract the data for them.
    # categorize_all_pdfs_in_folder("data/boa_cc", lambda pdf_path: categorize_pdf_to_csv_v1(pdf_path, extract_boa_transactions, categorize_boa, model))
    # categorize_all_pdfs_in_folder("data/schwab", lambda pdf_path: categorize_pdf_to_csv_v1(pdf_path, extract_schwab_transactions, categorize_schwab, model))
    # categorize_all_pdfs_in_folder("data/barclays", lambda pdf_path: categorize_pdf_to_csv_v1(pdf_path, extract_barclays_transactions, categorize_barclays, model))
    # categorize_all_pdfs_in_folder("data/paypal", lambda pdf_path: categorize_pdf_to_csv_v1(pdf_path, extract_paypal_transactions, categorize_paypal, model))

    categorize_all_pdfs_in_folder("data/boa_cc", lambda pdf_path: categorize_pdf_to_csv_v2(pdf_path, extract_dataframes, categorize.categorize, model))
    categorize_all_pdfs_in_folder("data/schwab", lambda pdf_path: categorize_pdf_to_csv_v2(pdf_path, extract_dataframes, categorize.categorize, model))
    categorize_all_pdfs_in_folder("data/barclays", lambda pdf_path: categorize_pdf_to_csv_v2(pdf_path, extract_dataframes, categorize.categorize, model))
    categorize_all_pdfs_in_folder("data/paypal", lambda pdf_path: categorize_pdf_to_csv_v2(pdf_path, extract_dataframes, categorize.categorize, model))


    # then gather all csvs that the pdfs generated
    csvs = []
    boa_csvs = all_csvs_in_folder("data/boa_cc")
    csvs.extend(boa_csvs)
    schwab_csvs = all_csvs_in_folder("data/schwab")
    csvs.extend(schwab_csvs)
    barclays_csvs = all_csvs_in_folder("data/barclays")
    csvs.extend(barclays_csvs)
    paypal_csvs = all_csvs_in_folder("data/paypal")
    csvs.extend(paypal_csvs)

    # now get the csvs of the month you want
    # relevant_csvs = [csv for csv in csvs if "Jan-2025" in csv or "2025-01" in csv]
    # or just get all of them
    relevant_csvs = csvs
    rollup_csv = []
    data = {}
    for csv_file_path in relevant_csvs:
        csv_data_df = read_csv(csv_file_path)
        records = csv_data_df.to_dict('records')
        for record in records:
            record['source'] = csv_file_path
        rollup_csv.extend(records)
        # print(f'\nProcessing csv {csv_file_path}\n{csv_data_df}\n')
        data = count_categories(csv_data_df, data)
    # Write csv to file
    export_to_csv(rollup_csv, 'rollup.csv')
    print("\n")
    # ouput sankeymatic for copying
    print(fmt_sankeymatic(data))

if __name__ == "__main__":
    main()
