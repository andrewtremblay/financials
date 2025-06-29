from langchain_community.document_loaders import PyPDFLoader
from langchain_core.output_parsers import StrOutputParser
import pandas as pd
import re
import os
import glob
import math
from pprint import pprint 


def load_pdf(pdf_path):
    """
    Loads a PDF file and returns its content as a list of documents.

    Args:
        pdf_path (str): The path to the PDF file to be loaded.

    Returns:
        list: A list of documents extracted from the PDF file.
    """

    print(f"Reading file '{pdf_path}'")
    loader = PyPDFLoader(pdf_path)
    documents = loader.load()
    return documents

def all_files_with_extensions(folder_path, extensions):
    all_files = []
    for ext in extensions:
        files = glob.glob(os.path.join(folder_path,ext))
        all_files.extend(files)
    return all_files


def all_pdfs_in_folder(folder_path):
    # Use glob to find all PDF files in the folder
    # Sometimes PDFs have capitalized extensions
    return all_files_with_extensions(folder_path, ['*.pdf', '*.PDF'])

def all_csvs_in_folder(folder_path):
    # Use glob to find all csv files in the folder
    return all_files_with_extensions(folder_path, ['*.csv'])



def export_to_csv(data, output_path):
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
    print(f"Data exported to {output_path}")

def read_csv(csv_path):
    """
    Reads data from a CSV file at the given path.
    Returns a pandas DataFrame which can be converted to list
    or empty DataFrame if the file does not contain any info
    """
    try:
        return pd.read_csv(csv_path)
    except pd.errors.EmptyDataError:
        return pd.DataFrame()

def clean_numeric_amount(value, row):
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

def count_categories(csv_df, data = {}):
    """
    Takes a pandas DataFrame (csv_df) with columns for amount and category and updates a dictionary (data) with the total amount for each category.
    The dictionary is expected to have an additional key "_map" which is a dictionary mapping subcategories to categories.
    The function returns the updated dictionary.
    """
    if "_map" not in data:
        data["_map"] = {}
    # expected to have an amount column and a category column
    for index, row in csv_df.iterrows():
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

def sort_budget(budget_data, meta):
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

INCOME_CATEGORIES = ["WAGES", "QUIZZIAI", "POSH", "SALARY", "TAKE_HOME_PAY"]


capitalization_map = {
    "ATM_WITHDRAWAL": "ATM Withdrawal",
    "MBTA": "MBTA",
    "CHATGPT": "ChatGPT",
} 

def fmt_capitalize(with_underscores):
    if with_underscores in capitalization_map:
        return capitalization_map[with_underscores]
    words = with_underscores.split("_")
    return " ".join(word.capitalize() for word in words)

# Outputs all categories as a sankeymatic string
# WAGES is a special category that we feed into budget
# All other categories are considered expenses coming out of budget
def fmt_sankeymatic(data):
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
    subcategories = data['_map'].keys()
    
    sankeymatic_str = ""    
    for category, amount in data.items():
        if category in ['_map'] or category in subcategories:
            continue
        if category in INCOME_CATEGORIES:
            wages_total += amount
        if category not in INCOME_CATEGORIES:
            total_expenses += amount
            sankeymatic_str += f"Budget [{amount}] {category}\n"
    sankeymatic_str += "\n"
    # Add overspending as an expense if we overspent
    if total_expenses > wages_total:
        sankeymatic_str += f"\nOverspending [{total_expenses - wages_total}] Budget\n"
    # Add savings if we didn't overspend
    if total_expenses < wages_total:
        sankeymatic_str += f"\nBudget [{wages_total - total_expenses}] Savings\n"
    sankeymatic_str += f"\nWages [{wages_total}] Budget\n"
    # go through the subcategories in _map
    if '_map' in data:
        for subcategory, category in data['_map'].items():
            if subcategory in data:
                if subcategory in INCOME_CATEGORIES:
                    sankeymatic_str += f"\n{subcategory} [{data[subcategory]}] {category}\n"
                else: 
                    sankeymatic_str += f"\n{category} [{data[subcategory]}] {subcategory}\n"
    return sort_budget(sankeymatic_str, data['_map'])



# Common output parser
output_parser = StrOutputParser()



CATEGORY_PROMPT =  "Categorize the following transaction, for example STOP & SHOP are Groceries and SHELL OIL is Gas. "
TRANSACTION_PARAM = "\n {transaction}"
UNCERTAINTY = "If you are less than 100 percent certain of the category, return 'INPUT NEEDED'."
ONLY_PRINT_CATEGORY = "Print no other text than the category. "
CATEGORY_SINGLE_WORD = "Categories must be single words whenver possible and as short as possible ('HOTEL', not 'HOTEL ACCOMODATION'). "
CATEGORY_UPPERCASE = "Categories must be in UPPERCASE. "


def extract_date_and_amount_from_transaction(text):
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


def check_categorized_data(categorized_data):
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
        print(f'Input needed for {len(input_needed_data)} transactions')
        for datum in input_needed_data:
            pprint(datum)
        return input_needed_data
    else: 
        print(f'Confidently categorized all {len(categorized_data)} transactions')
        return None



