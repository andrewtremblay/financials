from memo import memoized_invoke_chain_transaction
from utils import CATEGORY_PROMPT, TRANSACTION_PARAM, UNCERTAINTY, ONLY_PRINT_CATEGORY, CATEGORY_SINGLE_WORD, CATEGORY_UPPERCASE, output_parser, extract_date_and_amount_from_transaction
from langchain_core.prompts import PromptTemplate
import re


PAYPAL_IGNORE_BLOCKS = []


BILL_CATEGORIES = "Valve is a GAMES category. "
SUBSCRIPTION_CATEGORIES = "Spotify is a SUBSCRIPTION category. "

paypal_prompt = PromptTemplate.from_template(CATEGORY_PROMPT 
    + BILL_CATEGORIES 
    + SUBSCRIPTION_CATEGORIES 
    + CATEGORY_UPPERCASE 
    + UNCERTAINTY 
    + CATEGORY_SINGLE_WORD 
    + ONLY_PRINT_CATEGORY 
    + TRANSACTION_PARAM)




def extract_paypal_transactions(documents):
    transactions = []
    for page in documents:
        text = page.page_content
        # Regex to capture payment activities
        payment_pattern = re.compile(
            r"(\d{2}/\d{2}/\d{4})\s+(.+?)\s+(\d+\.\d{2})\s+USD",
            # r"(\d{2}/\d{2}/\d{4})\s+(.+?)\s+USD\s+-([\d,]+\.\d{2})",
            re.DOTALL
        )

        # Find all matches
        matches = payment_pattern.findall(text)

        # Process and display the extracted payments
        for match in matches:
            date, description, amount = match
            # Remove the unwanted phrase from the description
            description = re.sub(r"PreApproved Payment Bill User Payment:\s*", "", description)
            description = re.sub(r"\s+", " ", description.strip())  # Normalize multiline descriptions
            transactions.append(f"{date} {description} {amount}")

    return transactions



def convert_paypal_extract_data(text):
    transaction_pattern = re.compile(
        r"(\d{2}/\d{2}/\d{4})\s+(.+?)\s+(\d+\.\d{2})",
        re.DOTALL
    )
    matches = transaction_pattern.findall(text)
    for match in matches:
        date, description, amount = match
        return (date, description, amount)
    return None


def convert_paypal_extract_description(text):
    result = convert_paypal_extract_data(text)
    if result is not None:
        date, description, amount = result
        return description
    return ""


def categorize_paypal(model, transactions):
    chain = paypal_prompt | model | output_parser

    categorized_data = []
    for transaction in transactions:
        description = convert_paypal_extract_description(transaction)
        category = memoized_invoke_chain_transaction(chain, description)
        # unmemoized result:
        # category = chain.invoke({
        #     "transaction": description,
        # }).strip()
        # print("PAYPAL category:\t" + category)
        extracted = convert_paypal_extract_data(transaction)
        if extracted is None:
            categorized_data.append({"raw_transaction": transaction, "description": transaction_description, "category": category})
        else:
            # extracted result regext had the proper format
            categorized_data.append({"raw_transaction": transaction, "description": description, "date": extracted[0], "amount": extracted[2], "category": category})

    return categorized_data
