import pandas as pd


def load_user_file(file_path):

    try:

        if file_path.lower().endswith(".csv"):

            df = pd.read_csv(file_path)

        elif file_path.lower().endswith(".xlsx"):

            sheets = pd.read_excel(file_path, sheet_name=None)

            df = pd.concat(sheets.values(), ignore_index=True)

        else:

            raise ValueError("Unsupported file format. Use CSV or XLSX.")

        if len(df) == 0:
            raise ValueError("Uploaded file is empty.")

        return df

    except Exception as e:

        raise ValueError(f"Error loading file: {str(e)}")