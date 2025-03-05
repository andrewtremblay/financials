from memo import memoized_invoke_chain_transaction
from utils import CATEGORY_PROMPT, TRANSACTION_PARAM, UNCERTAINTY, ONLY_PRINT_CATEGORY, CATEGORY_SINGLE_WORD, CATEGORY_UPPERCASE,  output_parser, extract_date_and_amount_from_transaction
from langchain_core.prompts import PromptTemplate
import re
from pprint import pprint

# SCHWAB exports both pdf and csv files. The pdfs are in the same folder as the csvs.
# PDFs are harder to parse, but have transactions in a consistent billing period.

# this string means we found a SCHWAB Activity table
SCHWAB_BEGINNING_BALANCE = "Beginning Balance"
SCHWAB_ENDING_BALANCE = "Ending Balance"
SCHWAB_IGNORE_BLOCKS = [SCHWAB_BEGINNING_BALANCE, SCHWAB_ENDING_BALANCE]

SCHWAB_DEPOSIT = "Deposit"
SCHWAB_WITHDRAWAL = "Withdrawal"


# Prompt variables
SCHWAB_CATEGORIES = "BARCLAYCARD US CREDITCARD is a CREDIT CARD PAYMENT. "
IGNORE_CATEGORIES = "ZELLE TO CATHERINE PICCININNI is a IGNORE category. HONEYBEE.RENTAL is a IGNORE category. PAYPAL is a IGNORE category. "
BILL_CATEGORIES = "BUNKERHILL and PLYMOUTH ROCK are INSURANCE BILL categories. UNIPAYFEE ONE FEE is a UTILITIES BILL."
CHECK_CATEGORIES = "Check Paid is a CHECK category. "
SUBSCRIPTION_CATEGORIES = "1PASSWORD and APPLE.COM are each a SUBSCRIPTION category. "
OTHER_CATEGORIES = "ATHENA DIRECT DEP and GUSTO are WAGES category. A.L. PRIME is a GAS category. "

schwab_prompt = PromptTemplate.from_template(CATEGORY_PROMPT
    + SCHWAB_CATEGORIES 
    + IGNORE_CATEGORIES 
    + BILL_CATEGORIES 
    + SUBSCRIPTION_CATEGORIES 
    + CHECK_CATEGORIES 
    + OTHER_CATEGORIES 
    + CATEGORY_UPPERCASE 
    + UNCERTAINTY 
    + CATEGORY_SINGLE_WORD 
    + ONLY_PRINT_CATEGORY 
    + TRANSACTION_PARAM)


    
def convert_schwab_remove_running_total(text):
    return re.sub(r"\$([\d,]+\.\d{2})$", r"", text)

def remove_newlines(text):
    return re.sub(r"\s+", r" ", re.sub(r"\n", r" ", text))



def process_transaction(transaction):
    return convert_schwab_remove_running_total(remove_newlines(transaction.strip())).strip()


def extract_schwab_transactions(documents):
    """
    Take a list of Document objects, each representing a page of text,
    and return two lists: the first list contains income transactions
    and the second list contains expense transactions.

    The PDFs exported from Schwab have a consistent format, with
    transactions listed in a table. This function extracts that table
    and returns its contents as two lists: income and expenses.

    The income list will contain transactions that have the string
    "Deposit" or "Interest Paid" in them.

    The expenses list will contain transactions that have the string
    "Withdrawal" in them.

    The function will print out the original and mapped transactions
    for debugging purposes.

    :param documents: a list of Document objects
    :return: two lists, income and expenses, each containing strings
    """
    transactions = []
    for page in documents:
        text = page.page_content
        # inspect one line at a time
        lines = text.split("\n")

        full_transaction_pattern = re.compile(r"^(\d{2}\/\d{2})\s+(.+?)\s+\$([\d,]+\.\d{2})")
        # Some transactions are split across three lines
        # detecting part 1 starts another transaction gathering process
        part1_transaction_pattern = re.compile(r"^(\d{2}\/\d{2})\s+(.+?)$")

        # used for tracking partial transactions across multiple lines
        line_count = 0
        partial_transaction = ""
        for line in lines:
            
            if any(ignored_block in line for ignored_block in SCHWAB_IGNORE_BLOCKS):
                continue
            if line_count > 0:  # found part 1 in the last iteration, scan the next two lines
                partial_transaction = partial_transaction + " " + line
                line_count = line_count + 1
                if line_count == 3:
                    line_count = 0
                    transactions.append(partial_transaction)
                    partial_transaction = ""
                continue
            # check line
            full_match = full_transaction_pattern.match(line)
            part1_match = part1_transaction_pattern.match(line)
            if (full_match == None and part1_match == None):
                # no match, reset and return
                line_count = 0
                partial_transaction = ""
                continue
            if full_match != None:
                line_count = 0
                partial_transaction = ""
                # full match: we have a complete transaction
                transactions.append(line)
                continue
            if part1_match != None:
                # part 1 of match found
                line_count = 1
                partial_transaction = line
                continue

    mapped_transactions = list(map(process_transaction, transactions))
    return mapped_transactions

def convert_schwab_extract_description(text):
    """
    Schwab transactions come with some extra information on the left and right. 
    We only want the description of the transaction for categorization.
    11/07 [description] $99.99
    04/45 [description] $1,222.00
    We remove the date on the left and the $XXXX.XX on the right
    There is also a six digit number within the description, usually on the end but sometimes within the description. 
    We remove that as well.
    """
    return re.sub(r"\d{6}", "", re.sub(r"^\d{2}/\d{2} |\s\$[\d,.-]+\.\d{2}$", "", text.strip())).strip()


def categorize_schwab(model, transactions):
    chain = schwab_prompt | model | output_parser

    categorized_data = []
    for transaction in transactions:
        # print(f"'{transaction}'")
        transaction_type = "unknown"
        if SCHWAB_DEPOSIT in transaction or "Interest Paid" in transaction:
            transaction_type = 'income'
        if SCHWAB_WITHDRAWAL in transaction:
            transaction_type = 'expense'

        transaction_description = convert_schwab_extract_description(transaction)
        # print(f"analyzing description: '{transaction_description}'")
        result = memoized_invoke_chain_transaction(chain, transaction_description)
        # unmemoized result:
        # result = chain.invoke({
        #     "transaction": transaction_description,
        # }).strip()
        extracted_result = extract_date_and_amount_from_transaction(transaction)
        if extracted_result is None:
            categorized_data.append({"raw_transaction": transaction, "transaction_type": transaction_type, "description": transaction_description, "category": result})
        else:
            # extracted result regext had the proper format
            categorized_data.append({"raw_transaction": transaction,"transaction_type": transaction_type,  "description": transaction_description, "date": extracted_result[0], "amount": extracted_result[1], "category": result})

    return categorized_data
