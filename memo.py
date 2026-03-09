import json
import hashlib
from pathlib import Path

import pandas as pd

# File to store memoized results for descriptions
MEMO_DESCRIPTIONS_FILE = Path("memoized_descriptions_to_categories.json")
# File to store memoized results for dataframes
MEMO_DATAFRAME_FILE = Path("memoized_files_to_dataframes.json")

# Load existing memoized results or initialize an empty dictionary
if MEMO_DESCRIPTIONS_FILE.exists():
    with open(MEMO_DESCRIPTIONS_FILE, "r") as file:
        memoized_description_data = json.load(file)
else:
    memoized_description_data = {}

# Load existing memoized results or initialize an empty dictionary
if MEMO_DATAFRAME_FILE.exists():
    with open(MEMO_DATAFRAME_FILE, "r") as file:
        memoized_df_data = json.load(file)
else:
    memoized_df_data = {}


def memoize_description_to_file(func):
    """Decorator to memoize chain function results to a file."""
    def wrapper(chain, description):
        result = None
        # Create a unique key based on the description and chain
        description_key = f"{description}"
        chain_specific_key = hashlib.sha256(f"{chain}|{description}".encode()).hexdigest()
        if description_key in memoized_description_data:
            # print(f"memoized result for '{description_key}'")
            result = memoized_description_data[description_key]
        # Check if the result is already memoized
        if chain_specific_key in memoized_description_data:
            # print(f"memoized result for '{description_key}'")
            # print("Cached result: " + memoized_description_data[key])
            result = memoized_description_data[chain_specific_key]
        # Invoke the function and store the result
        if result is None:
            # print(f"cache miss for '{description}'")
            result = func(chain, description)
        # Add the result to the memoized dictionary
        memoized_description_data[chain_specific_key] = result
        memoized_description_data[description_key] = result
        # Save updated memoized data to file
        with open(MEMO_DESCRIPTIONS_FILE, "w") as file:
            json.dump(memoized_description_data, file, indent=4)
        
        return result
    return wrapper


def memoize_dataframe_to_file(func):
    """Decorator to memoize dataframe results to a file."""
    def wrapper(pdf_path):
        result = None
        # Create a unique key based on the description and chain
        key = f"{pdf_path}"
        if key in memoized_df_data:
            # print(f"memoized result for '{pdf_path}'")
            # Parse the JSON string
            parsed = json.loads(memoized_df_data[key])
            # Convert each JSON object (list of dicts) to a DataFrame
            result = [pd.DataFrame(data) for data in parsed]
        # Invoke the function and store the result
        if result is None:
            # print(f"cache miss for '{pdf_path}'")
            result: list[pd.DataFrame] = func(pdf_path)
        # Add the result to the memoized dictionary
        # Convert each DataFrame to a JSON dict
        json_list = [df.to_dict(orient='records') for df in result]
        # convert json_list to a JSON string
        memoized_df_data[key] = json.dumps(json_list)
        # Save updated memoized data to file
        with open(MEMO_DATAFRAME_FILE, "w") as file:
            json.dump(memoized_df_data, file, indent=4)
        return result
    return wrapper


@memoize_description_to_file
def memoized_invoke_chain_transaction(chain, transaction):
    """
    Memoize the result of invoking a chain with a given transaction.

    Parameters
    ----------
    chain : langchain.Chain
        The chain to invoke.
    transaction : str
        The transaction to pass to the chain.

    Returns
    -------
    result : dict
        The result of invoking the chain with the given transaction.
    """
    return chain.invoke({
        "transaction": transaction,
    }).strip() # sometimes strings come in with random spaces or newlines
