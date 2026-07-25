from memo import memoized_invoke_chain_transaction
from utils import CATEGORY_PROMPT, TRANSACTION_PARAM, UNCERTAINTY, ONLY_PRINT_CATEGORY, CATEGORY_SINGLE_WORD, CATEGORY_UPPERCASE, output_parser, extract_date_and_amount_from_transaction, load_local_category_hints
from langchain_core.prompts import PromptTemplate

BA_CATEGORIES = "BA ELECTRONIC PAYMENT is a CREDIT CARD PAYMENT. "
BILL_CATEGORIES = "ATT is a PHONE BILL. "
INTEREST_CATEGORIES = "INTEREST CHARGED is a INTEREST category. "
SUBSCRIPTION_CATEGORIES = "1PASSWORD and APPLE.COM are each a SUBSCRIPTION category. "
# Personal merchant/payee hints come from a gitignored local file (see
# category_hints.example.txt), never from committed source.
LOCAL_CATEGORY_HINTS = load_local_category_hints()

categorize_prompt = PromptTemplate.from_template(CATEGORY_PROMPT
    + BA_CATEGORIES
    + BILL_CATEGORIES
    + SUBSCRIPTION_CATEGORIES
    + INTEREST_CATEGORIES
    + LOCAL_CATEGORY_HINTS
    + CATEGORY_UPPERCASE
    + UNCERTAINTY 
    + CATEGORY_SINGLE_WORD 
    + ONLY_PRINT_CATEGORY 
    + TRANSACTION_PARAM)


def categorize(model: any, transactions: list[list[str]]) -> list[dict]:
    chain = categorize_prompt | model | output_parser
    categorized_data = []
    for transaction in transactions:
        raw_transaction = f"{transaction}"
        if(len(transaction) != 3):
            raise Exception(f"Invalid transaction: {raw_transaction}")
        date = transaction[0]
        description = transaction[1]
        amount = transaction[2]
        category = memoized_invoke_chain_transaction(chain, description)
        categorized_data.append({"raw_transaction": raw_transaction, "description": description, "date": date, "amount": amount, "category": category})

    return categorized_data
