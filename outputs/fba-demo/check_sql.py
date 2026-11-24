from bjc import sf_db
print(sf_db('SELECT compatibility_level FROM sys.databases WHERE name=DB_NAME()'))
print(sf_db("SELECT COUNT(*) FROM STRING_SPLIT(N'a b c', N' ')"))
