

import pandas as pd
import matplotlib.pyplot as plt

plt.figure(
    figsize=(25,20))

df1= pd.read_csv("C:\\Users\\naflaki\\Documents\\ArcGisShowCases\\df1.csv")
df2= pd.read_csv("C:\\Users\\naflaki\\Documents\\ArcGisShowCases\\df2.csv")
df3= pd.read_csv("C:\\Users\\naflaki\\Documents\\ArcGisShowCases\\df3.csv")


for i, df in enumerate([df1, df2, df3], 1):

    plt.plot(df['Dist'], df['Fre'], label=f'df{i}', marker=True)
    plt.scatter(x=df['Dist'], y=df['Fre'])
    plt.xticks(rotation=90, ha='right')
    plt.subplots_adjust(bottom=0.4, top=0.99)
plt.legend()
plt.show()


# import pandas as pd
# import matplotlib.pyplot as plt
# df  = pd.read_csv("C:\\Users\\naflaki\\Documents\\ArcGisShowCases\\df1.csv")
# df.plot()  # plots all columns against index
# df.plot(kind='scatter',x='Loc',y='Dist') # scatter plot
# df.plot(kind='density')  # estimate density function
# # df.plot(kind='hist')  # histogram