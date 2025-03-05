from memo import memoized_invoke_chain_transaction
from utils import CATEGORY_PROMPT, TRANSACTION_PARAM, UNCERTAINTY, ONLY_PRINT_CATEGORY, CATEGORY_SINGLE_WORD, CATEGORY_UPPERCASE, output_parser
from langchain_core.prompts import PromptTemplate
import re
from pprint import pprint

# Barclays exports both pdf files. 

# this string means we found a BARCLAYS Activity table
PAYMENT_RECEIVED = 'Payment Received'
BARCLAYS_IGNORE_BLOCKS = [PAYMENT_RECEIVED]



# Prompt variables
BILL_CATEGORIES = "BUNKERHILL and PLYMOUTH ROCK are INSURANCE BILL categories. UNIPAYFEE ONE FEE is a UTILITIES BILL."
SUBSCRIPTION_CATEGORIES = "1PASSWORD and APPLE.COM are each a SUBSCRIPTION category. "
OTHER_CATEGORIES = "ATHENA DIRECT DEP and GUSTO are WAGES category. A.L. PRIME is a GAS category. "

barclays_prompt = PromptTemplate.from_template(BILL_CATEGORIES + SUBSCRIPTION_CATEGORIES + CATEGORY_UPPERCASE + UNCERTAINTY + CATEGORY_SINGLE_WORD + ONLY_PRINT_CATEGORY + TRANSACTION_PARAM)
    

def remove_newlines(text):
    return re.sub(r"\s+", r" ", re.sub(r"\n", r" ", text))


def process_transaction(transaction):
    return remove_newlines(transaction.strip()).strip()


def extract_barclays_transactions(documents):
    transactions = []
    transaction = None
    for page in documents:
        text = page.page_content
        # inspect one line at a time
        lines = text.split("\n")
        # transactions can span multiple lines. 
        transaction_pattern_begins = re.compile(r"^(\w{3} \d{2}) (\w{3} \d{2}) (.+?)$")
        # transactions always end with a dollar amount with two decimal places
        # negative amounts are allowed but precede the dollar symbol
        transaction_pattern_ends = re.compile(r"-?\$([\d,]+\.\d{2})")
        # Format and display the matches
        for line in lines:
            if any(ignored_block in line for ignored_block in BARCLAYS_IGNORE_BLOCKS):
                continue
            if transaction is not None:
                # we have a multiline transaction
                # add the line no matter what it contains
                transaction += line
                if transaction_pattern_ends.search(line):
                    # we have reached the end of the transaction
                    transactions.append(transaction)
                    transaction = None
                continue
            if transaction_pattern_begins.match(line):
                # we have a new transaction
                transaction = line
                # early exit check for transactions that are on a single line
                if transaction_pattern_ends.search(line):
                    # immediately end the transaction
                    transactions.append(transaction)
                    transaction = None
                # else we have a multiline 
                continue
                
            # else we have a non-transaction line
    if transaction is not None:
        print(f"WARNING : Unfinished transaction: '{transaction}'")

    mapped_transactions = list(map(process_transaction, transactions))
    return mapped_transactions

def remove_delta_points(text):
    return re.sub(r"\s\d+$", r"", text)

def convert_barclays_extract_description(text):
    """
    We only want the description of the transaction for categorization.
    Oct 07 Oct 09 [description] ### $##.##
    Jan 15 Jan 15 [description] ## $#,###.##
    We remove the dates on the left and the points earned on the right
    """
    return re.sub(r"^(\w{3} \d{2}) (\w{3} \d{2})|\s\d+$", "", re.sub(r"-?\$([\d,]+\.\d{2})", "", text.strip()).strip()).strip()

def extract_word_date_and_amount_from_transaction(text):
    """
    Extracts the date and amount from a transaction string.

    Args:
        text (str): The transaction string, expected to contain a date in the format MMM DD
                    followed by an amount in the format -X,XXX.XX or X,XXX.XX.

    Returns:
        tuple: A tuple containing the extracted date (str) and amount (str) if found,
               otherwise None if the extraction fails.
    """
    match = re.search(r"^(\w{3} \d{2}).*?\$([\d,]+\.\d{2})$", text.strip())
    if match is not None:
        leading_date = match.group(1)
        trailing_amount = match.group(2)
        return (leading_date, trailing_amount)
    print(f"Could not extract word date or amount from text: '{text.strip()}'")
    return None


def categorize_barclays(model, transactions):
    chain = barclays_prompt | model | output_parser

    categorized_data = []
    for transaction in transactions:
        # print(f"'{transaction}'")
        transaction_description = convert_barclays_extract_description(transaction)
        
        # print(f"analyzing description: '{transaction_description}'")
        result = memoized_invoke_chain_transaction(chain, transaction_description)
        # unmemoized result:
        # result = chain.invoke({
        #     "transaction": transaction_description,
        # }).strip()
        extracted_result = extract_word_date_and_amount_from_transaction(transaction)
        if extracted_result is None:
            categorized_data.append({"raw_transaction": transaction, "description": transaction_description, "category": result})
        else:
            # extracted result regext had the proper format
            categorized_data.append({"raw_transaction": transaction, "description": transaction_description, "date": extracted_result[0], "amount": extracted_result[1], "category": result})

    return categorized_data
