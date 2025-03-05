import json
import hashlib
from pathlib import Path

# File to store memoized results
MEMO_FILE = Path("memoized_results.json")

# Load existing memoized results or initialize an empty dictionary
if MEMO_FILE.exists():
    with open(MEMO_FILE, "r") as file:
        memoized_data = json.load(file)
else:
    memoized_data = {}

def memoize_invoke_to_file(func):
    """Decorator to memoize chain function results to a file."""
    def wrapper(chain, description):
        result = None
        # Create a unique key based on the description and chain
        description_key = f"{description}"
        chain_specific_key = hashlib.sha256(f"{chain}|{description}".encode()).hexdigest()
        if description_key in memoized_data:
            result = memoized_data[description_key]
        # Check if the result is already memoized
        if chain_specific_key in memoized_data:
            # print("Cached result: " + memoized_data[key])
            result = memoized_data[chain_specific_key]
        # Invoke the function and store the result
        if result is None:
            print("evaluating " + description)
            result = func(chain, description)
            print("result " + result)
        # Add the result to the memoized dictionary
        memoized_data[chain_specific_key] = result
        memoized_data[description_key] = result
        # Save updated memoized data to file
        with open(MEMO_FILE, "w") as file:
            json.dump(memoized_data, file, indent=4)
        
        return result
    return wrapper


@memoize_invoke_to_file
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
