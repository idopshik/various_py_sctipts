import re
from datetime import datetime, timedelta


path = "diler1.csv"
path_w = "fixed_date.csv"

pattern = r"(\w{17})(\s*)(\d{5})"

def readit():
    with open(path, "r", encoding="utf-8") as fin:
        lines = fin.readlines()
        for line in lines:
            fo = re.findall(pattern, line)
            # must be int
            found = int(fo[0]) if fo else None

            if found:
                converted_date = (datetime.utcfromtimestamp(0) + timedelta(found)).strftime("%d.%m.%Y")
                print(converted_date)
            print("\n")



def writeit():
    """check encoding, row notion for windows -  encoding="cp1251"   """
    cou = 0
    conv = 0

    with open (path_w, "w", encoding="utf-8") as fout:
        with open(path, "r", encoding="utf-8") as fin:
            lines = fin.readlines()
            for line in lines:
                cou +=1
                fo = re.findall(pattern, line)
                #  must be int
                found = int(fo[0][2]) if fo else None
                #  print(found)
                #  print(fo)


                if found:
                    conv += 1
                    converted_date = (datetime.utcfromtimestamp(0) + timedelta(found)).strftime("%d.%m.%Y")
                    print(converted_date)

                    line = line.replace(str(found),converted_date)

                fout.write(line)

    print(f"\ndone, {cou} lines processed, {conv} fixed")

#  readit()
writeit()
