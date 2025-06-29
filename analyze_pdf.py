# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "aiohttp==3.8.4",
#     "aiosignal==1.3.1",
#     "annotated-types==0.7.0",
#     "anyio==4.7.0",
#     "async-timeout==4.0.2",
#     "attrs==23.1.0",
#     "autopep8==2.0.2",
#     "backoff==2.2.1",
#     "black==23.3.0",
#     "certifi==2023.5.7",
#     "cffi==1.15.1",
#     "cfgv==3.3.1",
#     "charset-normalizer==3.2.0",
#     "click==8.1.4",
#     "dataclasses-json==0.5.7",
#     "deprecation==2.0.7",
#     "distlib==0.3.6",
#     "distro==1.9.0",
#     "et-xmlfile==1.1.0",
#     "filelock==3.12.2",
#     "frozenlist==1.3.3",
#     "greenlet==3.1.1",
#     "h11==0.14.0",
#     "httpcore==1.0.7",
#     "httpx>=0.27.0",
#     "httpx-sse==0.4.0",
#     "identify==2.5.24",
#     "idna==3.4",
#     "iniconfig==2.0.0",
#     "jiter==0.8.2",
#     "jsonpatch==1.33",
#     "jsonpointer==3.0.0",
#     "langchain==0.3.13",
#     "langchain-community==0.3.13",
#     "langchain-core==0.3.28",
#     "langchain-ollama==0.2.2",
#     "langchain-openai==0.2.14",
#     "langchain-text-splitters==0.3.4",
#     "langsmith==0.2.4",
#     "marshmallow==3.19.0",
#     "marshmallow-enum==1.5.1",
#     "monotonic==1.6",
#     "multidict==6.0.4",
#     "mypy==1.3.0",
#     "mypy-extensions==1.0.0",
#     "nodeenv==1.8.0",
#     "numpy==1.26.4",
#     "ollama==0.4.4",
#     "openai==1.58.1",
#     "openpyxl==3.1.1",
#     "orjson==3.10.12",
#     "packaging==24.2",
#     "pandas==2.2.3",
#     "pathspec==0.11.1",
#     "pillow==10.0.0",
#     "platformdirs==3.8.1",
#     "pluggy==1.2.0",
#     "pre-commit==3.3.3",
#     "pybind11==2.11.1",
#     "pycairo==1.24.0",
#     "pycodestyle==2.10.0",
#     "pycparser==2.21",
#     "pydantic==2.10.4",
#     "pydantic-core==2.27.2",
#     "pydantic-settings==2.7.0",
#     "pygobject==3.44.1",
#     "pypdf==5.1.0",
#     "pytest==7.3.1",
#     "python-dateutil==2.8.2",
#     "python-dotenv==0.21.1",
#     "pytz==2024.2",
#     "pyyaml==6.0",
#     "regex==2024.11.6",
#     "requests==2.31.0",
#     "requests-toolbelt==1.0.0",
#     "rudder-sdk-python==2.0.2",
#     "ruff==0.0.272",
#     "six==1.16.0",
#     "sniffio==1.3.1",
#     "sqlalchemy==2.0.36",
#     "tenacity==9.0.0",
#     "termcolor==2.3.0",
#     "tiktoken==0.8.0",
#     "tqdm==4.65.0",
#     "typer==0.9.0",
#     "typing-extensions==4.12.2",
#     "typing-inspect==0.9.0",
#     "tzdata==2024.2",
#     "urllib3==2.0.3",
#     "virtualenv==20.23.1",
#     "yarl==1.9.2",
# ]
# ///
from pprint import pprint
from langchain_openai import ChatOpenAI
from langchain_ollama import OllamaLLM
from utils import load_pdf, export_to_csv, check_categorized_data, all_pdfs_in_folder, all_csvs_in_folder, read_csv, count_categories, fmt_sankeymatic
from boa import categorize_boa, extract_boa_transactions
from schwab import categorize_schwab, extract_schwab_transactions
from barclays import categorize_barclays, extract_barclays_transactions
from paypal import categorize_paypal, extract_paypal_transactions
from dotenv import load_dotenv
# Load environment variables from .env file
load_dotenv()



# Models. TODO: parameterize this
# model = OllamaLLM(model="granite3.1-dense:8b", temperature=0.0, request_timeout=60)
# model = OllamaLLM(model="granite3.1-moe:latest", temperature=0.0, request_timeout=60)
# model = OllamaLLM(model="llama3:latest", temperature=0.0, request_timeout=60)
model = OllamaLLM(model="gemma2:27b", temperature=0.0, request_timeout=60) # Most accurate free model. Not very fast.  
# model = ChatOpenAI(model="gpt-4", temperature=0.0, request_timeout=60) # Works best, but slow & most expensive
# model = ChatOpenAI(model="gpt-4o-mini", temperature=0.0, request_timeout=60) # Works slightly faster than gpt-4, less accurate, still costs money


def extract_data_from_pdf(pdf_path, extract, categorize):
    documents = load_pdf(pdf_path)
    transactions = extract(documents)
    print(f'Extracted {len(transactions)} transactions')
    categorized_data = categorize(model, transactions)
    return categorized_data

def categorize_pdf_to_csv(pdf_path, extract, categorize):
    output_csv = pdf_path.replace(".pdf", "_categorized.csv").replace(".PDF", "_categorized.csv")
    categorized_data = extract_data_from_pdf(pdf_path, extract, categorize)
    check_categorized_data(categorized_data)
    export_to_csv(categorized_data, output_csv)

def categorize_all_pdfs_in_folder(pdf_folder, extract, categorize):
    pdfs = all_pdfs_in_folder(pdf_folder)
    for pdf_file in pdfs:
        print(f'\n\n\nProcessing {pdf_file}\n')
        categorize_pdf_to_csv(pdf_file, extract, categorize)


# Main function
def main():
    # First categorize all PDFs
    # Most LLMs are not really good at directly reading PDFs. We have to extract the data for them.
    categorize_all_pdfs_in_folder("data/boa_cc", extract_boa_transactions, categorize_boa)
    categorize_all_pdfs_in_folder("data/schwab", extract_schwab_transactions, categorize_schwab)
    categorize_all_pdfs_in_folder("data/barclays", extract_barclays_transactions, categorize_barclays)
    categorize_all_pdfs_in_folder("data/paypal", extract_paypal_transactions, categorize_paypal)

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
        print(f'\n\n\nProcessing {csv_file_path}\n{csv_data_df}\n')
        data = count_categories(csv_data_df, data)
    # Write csv to file
    export_to_csv(rollup_csv, 'rollup.csv')
    print("\n")
    # ouput sankeymatic for copying
    print(fmt_sankeymatic(data))

if __name__ == "__main__":
    main()
