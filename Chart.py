

import pandas as pd
import matplotlib.pyplot as plt

plt.figure(
    figsize=(25,20))

df1= pd.read_csv("C:\\Users\\naflaki\\Documents\\ArcGisShowCases\\df1.csv")
df2= pd.read_csv("C:\\Users\\naflaki\\Documents\\ArcGisShowCases\\df2.csv")
df3= pd.read_csv("C:\\Users\\naflaki\\Documents\\ArcGisShowCases\\df3.csv")


for i, df in enumerate([df1, df2, df3], 1):

    plt.plot(df['Loc'], df['Dist'], label=f'df{i}', marker=True)

plt.legend()
plt.show()
