from langchain_community.document_loaders import PyPDFLoader
from langchain_core.documents import Document
from docling.document_converter import DocumentConverter
from langchain_core.output_parsers import StrOutputParser
import pandas as pd
import re
import os
import glob
import math
from pprint import pprint

from memo import memoize_dataframe_to_file 

@memoize_dataframe_to_file
def load_pdf_as_dataframes(pdf_path: str) -> list[pd.DataFrame]: 
    print(f"Reading file '{pdf_path}'")    
    dataframes: list[pd.DataFrame] = []
    converter = DocumentConverter()
    conv_res = converter.convert(pdf_path)
    for table_ix, table in enumerate(conv_res.document.tables):
        table_df: pd.DataFrame = table.export_to_dataframe()
        full_table_text = table_df.to_markdown().lower()
        if(("date" in full_table_text or "activity posted" in full_table_text)
           and "description" in full_table_text 
           and ("amount" in full_table_text 
                or "total" in full_table_text 
                or "net" in full_table_text
                or 'balance' in full_table_text)):
            dataframes.append(table_df)
        else:
            print(f"Skipping table {table_ix} (invalid columns):\n {full_table_text[0:100]}...")
    return dataframes


def load_pdf(pdf_path) -> list[Document]:
    """
    Loads a PDF file and returns its content as PyPDFLoader documents.
    """
    loader = PyPDFLoader(pdf_path)
    documents = loader.load()
    return documents

def all_files_with_extensions(folder_path: str, extensions: list[str]) -> list[str]:
    all_files = []
    for ext in extensions:
        files = glob.glob(os.path.join(folder_path,ext))
        all_files.extend(files)
    return all_files


def all_pdfs_in_folder(folder_path) -> list[str]:
    # Use glob to find all PDF files in the folder
    # Sometimes PDFs have capitalized extensions
    return all_files_with_extensions(folder_path, ['*.pdf', '*.PDF'])

def all_csvs_in_folder(folder_path) -> list[str]:
    # Use glob to find all csv files in the folder
    return all_files_with_extensions(folder_path, ['*.csv'])



def export_to_csv(data: dict, output_path: str) -> None:
    """
    Exports data to a CSV file at the given path.

    Args:
        data (list): A list of dictionaries, where each dictionary contains a transaction and its category.
        output_path (str): The path to which the CSV file will be written.

    Returns:
        None
    """
    df = pd.DataFrame(data)
    df.to_csv(output_path, index=False)
    # print(f"Data exported to {output_path}")

def read_csv(csv_path: str):
    """
    Reads data from a CSV file at the given path.
    Returns a pandas DataFrame which can be converted to list
    or empty DataFrame if the file does not contain any info
    """
    try:
        return pd.read_csv(csv_path)
    except pd.errors.EmptyDataError:
        return pd.DataFrame()

def clean_numeric_amount(value: any, row: pd.Series):
    try:
        if isinstance(value, str):
             # Handle non-string values
            converted = float(value.replace(',', ''))
            if math.isnan(converted):
                print(f"{row.raw_transaction}: Value {value} could not be converted")
                return 0
            return converted
        elif isinstance(value, float):
            if math.isnan(value):
                print(f"{row.raw_transaction}: Float value {value} could not be converted")
                return 0
            return value
        elif isinstance(value, int):
            if math.isnan(value):
                print(f"{row.raw_transaction}: Integer value {value} could not be converted")
                return 0
            return value
        print(f"{row.raw_transaction}: Value {value} could not be converted")
        return 0 
    except AttributeError: 
        print(f"{row.raw_transaction}: Error converting {value}") 
        return 0


# when categorizing, we want to ignore certain categories so they aren't double counted or miscounted as an expense
# These categories are never subcategories
IGNORE_CATEGORY = ["IGNORE", "BANKING", "INTEREST", "INVESTMENT","VENMO_PAYMENT", "CASHOUT", "CREDIT_CARD_PAYMENT", "BANK_TRANSFER"]

def count_categories(csv_df: pd.DataFrame, data: dict = {}):
    """
    Takes a pandas DataFrame (csv_df) with columns for amount and category and updates a dictionary (data) with the total amount for each category.
    The dictionary is expected to have an additional key "_map" which is a dictionary mapping subcategories to categories.
    The function returns the updated dictionary.
    """
    if "_map" not in data:
        data["_map"] = {}
    # expected to have an amount column and a category column
    for _, row in csv_df.iterrows():
        category = row.category
        if category in IGNORE_CATEGORY:
            continue
        amount = clean_numeric_amount(row.amount, row)
        categories = row.category.split(" ")
        previous_category = None
        for sub_category in categories:
            if previous_category is not None: 
                # map parent category to subcategory
                data["_map"][sub_category] = previous_category
            previous_category = sub_category
            if sub_category in data:
                data[sub_category] += amount
            else:
                data[sub_category] = amount
            data[sub_category] = round(data[sub_category]) # round to highest number
    return data

def sort_budget(budget_data: list, meta: dict):
    pattern = re.compile(r"(\w+(?: \w+)*) \[(\d+)\](?: (\w+))?")
    parsed_data = [
        (match.group(1), int(match.group(2)), match.group(3) or "")
        for match in pattern.finditer(budget_data)
    ]

    # Sort the data by the numeric value (amount)
    # sorted_budget = sorted(parsed_data, key=lambda x: x[1])
    # or sort by category & name
    sorted_budget = sorted(parsed_data, key=lambda x: meta[x[0]] if x[0] in meta else f"{x[0]} {x[1]}")


    result = ""
    # Print the sorted data
    for item in sorted_budget:
        if(item[1] == 0):
            print(f"ERROR: zero value for {item[2]} ({item[0]}): skipping")
            continue
        if item[0] == 'Overbudget' or item[2] == 'Savings':
            # we always append these to the end
            continue
        result += f"{fmt_capitalize(item[0])} [{item[1]}] {fmt_capitalize(item[2])}\n"
    for item in sorted_budget:
        if item[0] == 'Overbudget' or item[2] == 'Savings':
            result += f"{fmt_capitalize(item[0])} [{item[1]}] {fmt_capitalize(item[2])}\n"
            break
    print('\n\n')
    return result

INCOME_CATEGORIES = ["WAGES", "INCOME", "ZUS", "ZUS_CREDIT", "SALARY", "TAKE_HOME_PAY"]


capitalization_map = {
    "ATM_WITHDRAWAL": "ATM Withdrawal",
    "MBTA": "MBTA",
    "CHATGPT": "ChatGPT",
} 

def fmt_capitalize(with_underscores: str):
    if with_underscores in capitalization_map:
        return capitalization_map[with_underscores]
    words = with_underscores.split("_")
    return " ".join(word.capitalize() for word in words)

# Outputs all categories as a sankeymatic string
# WAGES is a special category that we feed into budget
# All other categories are considered expenses coming out of budget
def fmt_sankeymatic(data: dict):
    """   
    Wages [1500] Budget
    Other [250] Budget

    Budget [450] Taxes
    Budget [420] Housing
    Budget [400] Food
    Budget [295] Fun 
    Budget [25] Savings
    Fun [25] Theater
    """
    # calcaulate wages total
    wages_total = 0
    total_expenses = 0
    
    data = dict(data)  # don't mutate caller's dict
    subcategories = dict()
    if '_map' in data:
        subcategories = data.pop('_map')
        
    # Expense parent nodes: categories that are values in _map (have sub-categories flowing out)
    # Compute how much of each parent's total is already accounted for by its subcategories.
    # Any remainder is a "direct" spend on the parent itself (no sub-category assigned).
    expense_sub_totals = {}  # parent -> sum of subcategory amounts
    for sub, parent in subcategories.items():
        if parent not in INCOME_CATEGORIES and sub in data:
            expense_sub_totals[parent] = expense_sub_totals.get(parent, 0) + data[sub]

    sankeymatic_str = ""
    for category, amount in data.items():
        if category in subcategories.keys():
            print(f"Skipping subcategory {category}")
            continue
        print(f"Processing category {category} with amount {amount}")
        if category in INCOME_CATEGORIES and amount != 0:
            wages_total += amount
            # Suppress only the WAGES→Wages self-loop; all other income categories
            # (including aggregators like ZUS) should still emit a flow into Wages.
            if fmt_capitalize(category) != "Wages":
                sankeymatic_str += f"{category} [{amount}] Wages\n"
        else:
            if amount <= 0:
                # Negative/zero net amounts (refunds that exceed purchases) would be dropped
                # by sort_budget's positive-integer regex, silently inflating savings.
                # Skip them entirely so total_expenses stays in sync with Sankey output.
                print(f"Skipping non-positive expense {category}: {amount}")
                continue
            # For parent nodes, sum their registered subcategories instead of
            # relying on the accumulated data value, so Budget flows are always
            # grounded in the actual sub-category hierarchy.
            effective = expense_sub_totals.get(category, amount)
            total_expenses += effective
            sankeymatic_str += f"Budget [{effective}] {category}\n"
    sankeymatic_str += "\n\n # TOTALS"
    sankeymatic_str += f"\nWages [{wages_total}] Budget\n"
    # Both savings and overspending are outflows from Budget (right side),
    # keeping Budget's left side as income only.
    if total_expenses > wages_total:
        sankeymatic_str += f"\nBudget [{total_expenses - wages_total}] Overspending\n"
    if total_expenses < wages_total:
        sankeymatic_str += f"\nBudget [{wages_total - total_expenses}] Savings\n"
    # go through the subcategories in _map
    for subcategory, category in subcategories.items():
        if subcategory in data and data[subcategory] != 0:
            if category in INCOME_CATEGORIES:
                # Sub is a paycheck source flowing INTO an income aggregator (e.g. ZUS)
                sankeymatic_str += f"\n{subcategory} [{data[subcategory]}] {category}\n"
            else:
                sankeymatic_str += f"\n{category} [{data[subcategory]}] {subcategory}\n"
    # For expense parent nodes, emit a "direct" flow for any spend that has no sub-category.
    # This keeps the Needs/Wants nodes balanced (inflow == outflow), analogous to Wages.
    # Use underscore suffix so sort_budget's single-word regex captures it correctly
    # (fmt_capitalize will render NEEDS_DIRECT → "Needs Direct").
    for parent, sub_total in expense_sub_totals.items():
        if parent in data:
            direct = data[parent] - sub_total
            if direct > 0:
                sankeymatic_str += f"\n{parent} [{direct}] {parent}_DIRECT\n"
    return sort_budget(sankeymatic_str, subcategories)



# Common output parser
output_parser = StrOutputParser()



CATEGORY_PROMPT =  "Categorize the following transaction, for example STOP & SHOP are Groceries and SHELL OIL is Gas. "
TRANSACTION_PARAM = "\n {transaction}"
UNCERTAINTY = "If you are less than 100 percent certain of the category, return 'INPUT NEEDED'."
ONLY_PRINT_CATEGORY = "Print no other text than the category. "
CATEGORY_SINGLE_WORD = "Categories must be single words whenver possible and as short as possible ('HOTEL', not 'HOTEL ACCOMODATION'). "
CATEGORY_UPPERCASE = "Categories must be in UPPERCASE. "


def extract_date_and_amount_from_transaction(text: str):
    """
    Extracts the date and amount from a transaction string.

    Args:
        text (str): The transaction string, expected to contain a date in the format MM/DD
                    followed by an amount in the format -X,XXX.XX or X,XXX.XX.

    Returns:
        tuple: A tuple containing the extracted date (str) and amount (str) if found,
               otherwise None if the extraction fails.
    """
    match = re.search(r"^(\d{2}/\d{2}).*?(-?[\d,]+\.\d{2})$", text.strip())
    if match:
        leading_date = match.group(1)
        trailing_amount = match.group(2)
        return (leading_date, trailing_amount)
    print(f"Could not extract date or amount from text: '{text}'")
    return None


def check_categorized_data(categorized_data: list[dict]):
    """
    Checks if any transactions in the categorized data need human input.

    Args:
        categorized_data (list): A list of dicts, each containing the raw transaction data
                                 and the automatically assigned category.

    Prints a message indicating if any transactions need human input, and if so,
    prints the raw data for each of those transactions.
    """
    input_needed_data = list(filter(lambda x: x['category'] == 'INPUT NEEDED', categorized_data))
    if len(input_needed_data) > 0:
        # print(f'Input needed for {len(input_needed_data)} transactions')
        for datum in input_needed_data:
            pprint(datum)
        return input_needed_data
    else: 
        # print(f'Confidently categorized all {len(categorized_data)} transactions')
        return None



