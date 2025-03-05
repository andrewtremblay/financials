from memo import memoized_invoke_chain_transaction
from utils import CATEGORY_PROMPT, TRANSACTION_PARAM, UNCERTAINTY, ONLY_PRINT_CATEGORY, CATEGORY_SINGLE_WORD, CATEGORY_UPPERCASE, output_parser, extract_date_and_amount_from_transaction
from langchain_core.prompts import PromptTemplate
import re


# this string means we found a BOA table
BOA_TABLE_HEADER = "TransactionsTransactionDate PostingDate Description ReferenceNumber"
BOA_TABLE_CONTINUED_HEADER = "Transactions ContinuedTransactionDate PostingDate Description ReferenceNumber"
BOA_PAYMENTS_AND_OTHER_CREDITS = "Payments and Other Credits"
BOA_PURCHASES_AND_ADJUSTMENTS = "Purchases and Adjustments"
BOA_INTEREST_CHARGED = "Interest Charged"
BOA_TOTAL_PAYMENTS = "TOTAL PAYMENTS AND OTHER CREDITS FOR THIS PERIOD"
BOA_TOTAL_PURCHASES = "TOTAL PURCHASES AND ADJUSTMENTS FOR THIS PERIOD"
BOA_IGNORE_BLOCKS = [BOA_TABLE_HEADER, BOA_TABLE_CONTINUED_HEADER, BOA_INTEREST_CHARGED, BOA_PAYMENTS_AND_OTHER_CREDITS, BOA_PURCHASES_AND_ADJUSTMENTS, BOA_TOTAL_PAYMENTS, BOA_TOTAL_PURCHASES]


BA_CATEGORIES = "BA ELECTRONIC PAYMENT is a CREDIT CARD PAYMENT. "
BILL_CATEGORIES = "ATT is a PHONE BILL. "
INTEREST_CATEGORIES = "INTEREST CHARGED is a INTEREST category. "
SUBSCRIPTION_CATEGORIES = "1PASSWORD and APPLE.COM are each a SUBSCRIPTION category. "
OTHER_CATEGORIES = "DENTE ENTERPRISES LLC and TA WEST GREENWICH are each a FOOD category. A.L. PRIME is a GAS category. "

boa_prompt = PromptTemplate.from_template(CATEGORY_PROMPT
    + BA_CATEGORIES 
    + BILL_CATEGORIES
    + SUBSCRIPTION_CATEGORIES 
    + INTEREST_CATEGORIES 
    + OTHER_CATEGORIES 
    + CATEGORY_UPPERCASE 
    + UNCERTAINTY 
    + CATEGORY_SINGLE_WORD 
    + ONLY_PRINT_CATEGORY 
    + TRANSACTION_PARAM)



def convert_boa_remove_arrival_date(text):
    return re.sub(r"ARRIVAL DATE \d{2}/\d{2}/\d{2}", "", text)

def convert_boa_extract_description(text):
    """
    BOA transactions come with some extra information on the left and right. 
    We only want the description of the transaction for categorization.
    In the format MM/DD MM/DD XXXX.XX
    We remove the dates and the XXXX XXXX XXXX.XX on the right
    """
    return re.sub(r"^\d{2}/\d{2} \d{2}/\d{2} |\s\d{4} \d{4} [\d,.-]+\.\d{2}$", "", text)

def convert_boa_dates_to_newlines(text):
    """
    BOA tables have dates in the format MM/DD but are almost never split into the newlines 
    So transactions come in as something like $1,00010/12 instead of $1,000\n10/12
    So they have to be converted.
    We split the first four digits into two parts with a newline after the first two digits.
    """
    return re.sub(r"(\d{2})(\d{2})/(\d{2})", r"\1\n\2/\3", text)

def convert_boa_remove_continued_string(text):
    return re.sub(r"continued on next page...", "", text)

def convert_boa_header_to_newlines(text):
    return re.sub(BOA_PAYMENTS_AND_OTHER_CREDITS, BOA_PAYMENTS_AND_OTHER_CREDITS + "\n", text)

def convert_boa_total_payments_to_newlines(text):
    return re.sub(BOA_TOTAL_PAYMENTS, "\n" + BOA_TOTAL_PAYMENTS, text)

def convert_boa_total_purchases_to_newlines(text):
    return re.sub(BOA_TOTAL_PURCHASES, "\n"+ BOA_TOTAL_PURCHASES + "\n", text)

def convert_boa_purchases_and_adjustments_to_newlines(text):
    return re.sub(BOA_PURCHASES_AND_ADJUSTMENTS, "\n" + BOA_PURCHASES_AND_ADJUSTMENTS + "\n", text)
def extract_boa_transactions(documents):
    transactions = []
    for page in documents:
        text = page.page_content
        lines = text.split("\n")
        # not all lines are actually transactions so we need to remove the ones that aren't
        for line in lines:
            if BOA_TABLE_HEADER in line or BOA_TABLE_CONTINUED_HEADER in line:
                # BOA TABLE HEADER shows that we have a block of text meant to be a table of transactions
                # we need to convert it to a list of transactions and we also trim out useless strings at the same time
                blocks = convert_boa_dates_to_newlines(
                    convert_boa_header_to_newlines(
                        convert_boa_total_payments_to_newlines(
                            convert_boa_total_purchases_to_newlines(
                                convert_boa_purchases_and_adjustments_to_newlines(    
                                   convert_boa_remove_continued_string(
                                        convert_boa_remove_arrival_date(line)
                                    )
                                )
                            )
                        )
                    )
                ).split("\n")
                for block in blocks:
                    if len(block) > 0 and not any(ignored_block in block for ignored_block in BOA_IGNORE_BLOCKS):
                        transactions.append(block)
                    # else:
                    #     print(block)
            # else:
            #     print(line)
    return transactions


def categorize_boa(model, transactions):
    chain = boa_prompt | model | output_parser

    categorized_data = []
    for transaction in transactions:
        transaction_description = convert_boa_extract_description(transaction)
        # print("BOA description:" + transaction_description)
        result = memoized_invoke_chain_transaction(chain, transaction_description)
        # unmemoized result:
        # result = chain.invoke({
        #     "transaction": transaction_description,
        # }).strip()
        # print("BOA result:\t" + result)
        extracted_result = extract_date_and_amount_from_transaction(transaction)
        if extracted_result is None:
            categorized_data.append({"raw_transaction": transaction, "description": transaction_description, "category": result})
        else:
            # extracted result regext had the proper format
            categorized_data.append({"raw_transaction": transaction, "description": transaction_description, "date": extracted_result[0], "amount": extracted_result[1], "category": result})

    return categorized_data
