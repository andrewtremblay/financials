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

    csvs = []
    # then gather all csvs that the pdfs generated
    boa_csvs = all_csvs_in_folder("data/boa_cc")
    csvs.extend(boa_csvs)
    schwab_csvs = all_csvs_in_folder("data/schwab")
    csvs.extend(schwab_csvs)
    barclays_csvs = all_csvs_in_folder("data/barclays")
    csvs.extend(barclays_csvs)
    paypal_csvs = all_csvs_in_folder("data/paypal")
    csvs.extend(paypal_csvs)

    # now get the csvs of the month you want
    relevant_csvs = [csv for csv in csvs if "Jan-2025" in csv or "2025-01" in csv]
    # or just get all of them
    # relevant_csvs = csvs
    # pprint(csvs_of_month)
    rollup_csv = []
    data = {}
    for csv_file_path in relevant_csvs:
        csv_data_df = read_csv(csv_file_path)
        rollup_csv.extend(csv_data_df.to_dict('records'))
        print(f'\n\n\nProcessing {csv_file_path}\n{csv_data_df}\n')
        data = count_categories(csv_data_df, data)
    # Write csv to file
    export_to_csv(rollup_csv, 'rollup.csv')
    print("\n")
    print(fmt_sankeymatic(data))
    # pdf_file = "data/paypal/statement-Nov-2024.pdf"
    # pdf_file = "data/paypal/statement-Oct-2024.pdf"
    # categorize_pdf_to_csv(pdf_file, extract_paypal_transactions, categorize_paypal)

if __name__ == "__main__":
    main()
