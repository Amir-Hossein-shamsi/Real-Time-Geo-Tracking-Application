from pymongo import MongoClient
client = MongoClient("mongodb://localhost:27017")
db = client["delivery"]
branches_col = db["branches"]

branches_col.insert_many([
    {"branchId": "B001", "name": "Branch A", "lat": 35.7034564672035, "lon": 51.41561887977937},
    {"branchId": "B002", "name": "Branch B", "lat": 35.70552529539049, "lon":  51.419416427147496},
    {"branchId": "B003", "name": "Branch C", "lat": 35.706634157875826, "lon": 51.40530566182447},
    {"branchId": "B004", "name": "Branch D", "lat": 35.70596884231521, "lon": 51.42239030877365},
    {"branchId": "B005", "name": "Branch E", "lat": 35.71668714072158, "lon":  51.41811156047253},
    {"branchId": "B006", "name": "Branch F", "lat": 35.73285005077543 , "lon":  51.377394476782776},
    {"branchId": "B007", "name": "Branch G", "lat": 35.700796108384154, "lon":  51.387571112466034},
    {"branchId": "B008", "name": "Branch H", "lat": 35.68543846529673, "lon":  51.42300889957598}
])
