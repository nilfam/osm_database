import os
import pickle

import pandas as pd
from progress.bar import Bar

original_columns = ['exp', 'prep', 'locatum', 'relatum', 'lcoords', 'rcoords', 'type', 'bearing', 'Distance',	'LocatumType', 'RelatumType']

result_all_rows_cache = 'result_all_rows.cache'

if os.path.exists(result_all_rows_cache):
    with open(result_all_rows_cache, 'rb') as f:
        cache = pickle.load(f)
        result_all_rows = cache['result_all_rows']
        previous_index = cache['previous_index']
        max_num_objects_same_name = cache['max_num_objects_same_name']
else:
    raise Exception('File is not ready')

print("Finish reading the cache")

result_file_columns = original_columns + ['Success ?', 'Reason for failure'] + ['', ''] * max_num_objects_same_name
result_df = pd.DataFrame(columns=result_file_columns)

bar = Bar("Constructing dataframe...", max=len(result_all_rows))

index = 0
for index, row in enumerate(result_all_rows):
    if index < 3100:
        bar.next()
        continue
    if len(row) < len(result_file_columns):
        for i in range(len(result_file_columns) - len(row)):
            row.append('')

    result_df.loc[index] = row
    index += 1
    bar.next()

bar.finish()

print("Writing dataframe to Excel")

output_file = 'CornerData__out__preliminary__from_3100-7800.xlsx'

writer = pd.ExcelWriter(output_file)
result_df.to_excel(excel_writer=writer, sheet_name='Sheet1', index=None)

writer.save()
