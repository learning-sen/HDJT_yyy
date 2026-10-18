import pyAether as ae
ae.emyInitAether("-adv")

#open design
cv = ae.dbOpenCV(lib="2026_EDA_case1", cell="OPA", view="schematic")
print(str(cv))
#ae.emyInitAether("-adv")

I_PM0 = ae.dbFindInst(cv, "PM0")
print(str(I_PM0))

for p in I_PM0.instTerms:
    if p.name=="G":
       print("PM0 Gate connect is", p.net.name)
    elif p.name =="S":
       print("PM0 Source connect is" ,p.net.name)
    elif p.name =="D":
       print("PM0 Drain connect is" ,p.net.name)
    else:
       print("PM0 Body connect is", p.net.name)
   
   
