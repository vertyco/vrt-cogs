import aiohttp
import json
import asyncio
import csv
import os
import pandas as pd


class Checker:
    @staticmethod
    async def check_part(items: list):
        async with aiohttp.ClientSession() as session:
            no_exist = []
            invalid = {
                "SKU Number": [],
                "Item Title": []
            }
            count = 0
            for item in items:
                sku = item['id']
                if count % 20 == 0:
                    print(f"{count} items checked")
                count += 1
                async with session.get(f"https://www.ebay.com/itm/{sku}") as resp:
                    info = await resp.text()
                    if "We looked everywhere" in str(info):
                        invalid["SKU Number"].append(sku)
                        invalid["Item Title"].append(item['title'])
                        no_exist.append([sku, item['title']])
                    else:
                        continue

            # print(no_exist)
            print(f"Checked {count} items, {len(no_exist)} items no longer exist.")

            # CSV module way
            # with open('non-existent-items.csv', 'w') as file:
            #     # create the csv writer
            #     writer = csv.writer(file)
            #     header = ['SKU', 'Item Title']
            #     writer.writerow(header)
            #     writer.writerows(no_exist)

            # PANDAS module way
            df = pd.DataFrame(invalid)
            writer = pd.ExcelWriter("non-existent-items.xlsx", engine='xlsxwriter')
            # Convert the dataframe to an XlsxWriter Excel object.
            df.to_excel(writer, sheet_name='Sheet1')

            # Get the xlsxwriter workbook and worksheet objects.
            workbook = writer.book
            worksheet = writer.sheets['Sheet1']

            # Add some cell formats.
            format1 = workbook.add_format({'num_format': '0'})

            # Note: It isn't possible to format any cells that already have a format such
            # as the index or headers or any cells that contain dates or datetimes.

            # Set the column width and format.
            worksheet.set_column(1, 1, 18, format1)

            # Close the Pandas Excel writer and output the Excel file.
            writer.save()

            return


try:
    os.remove('non-existent-items.csv')
except WindowsError:
    pass

f = open('items.json')
data = json.load(f)

c = Checker()
loop = asyncio.get_event_loop()
loop.run_until_complete(c.check_part(data))

