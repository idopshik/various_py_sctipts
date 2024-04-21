import re

path = "xgf1.csv"
path_w = "cleaned_xgf1.csv"
path_doubles = "doubles.csv"
pattern = r"^(\w*)(,)"

def readit():
    with open(path, "r", encoding="cp1251") as fin:
        lines = fin.readlines()
        for line in lines:
            found = re.findall(pattern, line)
            s_found = re.search(pattern, line)



            print(line)
            print(found)
            print("\n")



def writeit():
    """check encoding, row notion for windows -  encoding="cp1251"   """
    S = set()
    S.add(None)
    doules = []
    cou = 0
    wcou = 0
    dcou = 0
    with open(path, "r", encoding="utf-8") as fin:
        with open (path_w, "w", encoding="utf-8") as fout:
            lines = fin.readlines()
            for line in lines:
                cou +=1

                fo = re.findall(pattern, line)
                found = fo[0][0] if fo else None

                #  print(f"\n\n line {cou}, - found is {found}")
                if found:
                    if found not in S:
                        fout.write(line)
                        #  print(f" write as not in S - {line}")
                        wcou+=1
                    else:
                        #  print("debug")
                        #  print(found)
                        #  print(type(found))
                        #  print(f"S is: {S}")
                        doules.append(line)
                        #  print("appended as doubled, is it right????")
                else:
                    fout.write(line)
                    #  print(f"write as not found - {line}")
                    wcou+=1
                #  if cou > 2:
                    #  return

                S.add(found)
            dcou = len(doules)

    with open(path_doubles, "w", encoding="utf-8") as fout:
        fout.writelines(doules)


    print(f"\ndone, {cou} lines processed, {wcou} regular lines and {dcou} doubles")

#  readit()
writeit()
