"""Curated seed ports for Indian pharma export lanes.

Deliberately NOT the full UN/LOCODE registry (~100k entries would drown every
dropdown) — these are the gateways and destinations that actually occur in
this trade. The client extends the list from Settings.
(port_name, unlocode, mode, city, country)
"""

SEED_PORTS = [
	# — Indian gateways: sea —
	("Nhava Sheva (JNPT)", "INNSA", "Sea", "Navi Mumbai", "India"),
	("Mundra", "INMUN", "Sea", "Mundra", "India"),
	("Mumbai Port", "INBOM", "Sea", "Mumbai", "India"),
	("Chennai", "INMAA", "Sea", "Chennai", "India"),
	("Kattupalli", "INKAT", "Sea", "Chennai", "India"),
	("Tuticorin", "INTUT", "Sea", "Thoothukudi", "India"),
	("Cochin", "INCOK", "Sea", "Kochi", "India"),
	("Hazira", "INHZA", "Sea", "Surat", "India"),
	("Pipavav", "INPAV", "Sea", "Pipavav", "India"),
	("Kolkata", "INCCU", "Sea", "Kolkata", "India"),
	("Visakhapatnam", "INVTZ", "Sea", "Visakhapatnam", "India"),
	("ICD Tughlakabad", "INTKD", "Sea", "New Delhi", "India"),
	# — Indian gateways: air —
	("Mumbai Air Cargo (CSMIA)", "INBOM-A", "Air", "Mumbai", "India"),
	("Delhi Air Cargo (IGI)", "INDEL", "Air", "New Delhi", "India"),
	("Hyderabad Air Cargo (RGIA)", "INHYD", "Air", "Hyderabad", "India"),
	("Chennai Air Cargo", "INMAA-A", "Air", "Chennai", "India"),
	("Bengaluru Air Cargo", "INBLR", "Air", "Bengaluru", "India"),
	("Ahmedabad Air Cargo", "INAMD", "Air", "Ahmedabad", "India"),
	# — Gulf / Middle East —
	("Jebel Ali", "AEJEA", "Sea", "Dubai", "United Arab Emirates"),
	("Dubai Air Cargo (DXB)", "AEDXB", "Air", "Dubai", "United Arab Emirates"),
	("Sharjah", "AESHJ", "Sea & Air", "Sharjah", "United Arab Emirates"),
	("Jeddah", "SAJED", "Sea", "Jeddah", "Saudi Arabia"),
	("Dammam", "SADMM", "Sea", "Dammam", "Saudi Arabia"),
	("Riyadh Air Cargo", "SARUH", "Air", "Riyadh", "Saudi Arabia"),
	("Hamad Port", "QAHMD", "Sea", "Doha", "Qatar"),
	("Shuwaikh", "KWSWK", "Sea", "Kuwait City", "Kuwait"),
	("Sohar", "OMSOH", "Sea", "Sohar", "Oman"),
	("Aqaba", "JOAQJ", "Sea", "Aqaba", "Jordan"),
	# — Africa —
	("Apapa (Lagos)", "NGAPP", "Sea", "Lagos", "Nigeria"),
	("Lagos Air Cargo (MMIA)", "NGLOS", "Air", "Lagos", "Nigeria"),
	("Tema", "GHTEM", "Sea", "Tema", "Ghana"),
	("Accra Air Cargo", "GHACC", "Air", "Accra", "Ghana"),
	("Mombasa", "KEMBA", "Sea", "Mombasa", "Kenya"),
	("Nairobi Air Cargo (JKIA)", "KENBO", "Air", "Nairobi", "Kenya"),
	("Dar es Salaam", "TZDAR", "Sea", "Dar es Salaam", "Tanzania"),
	("Durban", "ZADUR", "Sea", "Durban", "South Africa"),
	("Johannesburg Air Cargo (ORTIA)", "ZAJNB", "Air", "Johannesburg", "South Africa"),
	("Addis Ababa Air Cargo", "ETADD", "Air", "Addis Ababa", "Ethiopia"),
	("Alexandria", "EGALY", "Sea", "Alexandria", "Egypt"),
	("Cairo Air Cargo", "EGCAI", "Air", "Cairo", "Egypt"),
	# — Europe —
	("Hamburg", "DEHAM", "Sea", "Hamburg", "Germany"),
	("Frankfurt Air Cargo", "DEFRA", "Air", "Frankfurt", "Germany"),
	("Rotterdam", "NLRTM", "Sea", "Rotterdam", "Netherlands"),
	("Antwerp", "BEANR", "Sea", "Antwerp", "Belgium"),
	("Felixstowe", "GBFXT", "Sea", "Felixstowe", "United Kingdom"),
	("London Heathrow Air Cargo", "GBLHR", "Air", "London", "United Kingdom"),
	("Ambarli (Istanbul)", "TRAMR", "Sea", "Istanbul", "Turkey"),
	# — Americas —
	("New York / Newark", "USNYC", "Sea", "New York", "United States"),
	("Houston", "USHOU", "Sea", "Houston", "United States"),
	("Los Angeles", "USLAX", "Sea", "Los Angeles", "United States"),
	("Chicago Air Cargo (ORD)", "USORD", "Air", "Chicago", "United States"),
	("Santos", "BRSSZ", "Sea", "Santos", "Brazil"),
	("Sao Paulo Air Cargo (GRU)", "BRGRU", "Air", "Sao Paulo", "Brazil"),
	("Buenos Aires", "ARBUE", "Sea", "Buenos Aires", "Argentina"),
	("Veracruz", "MXVER", "Sea", "Veracruz", "Mexico"),
	# — Asia —
	("Singapore", "SGSIN", "Sea & Air", "Singapore", "Singapore"),
	("Port Klang", "MYPKG", "Sea", "Port Klang", "Malaysia"),
	("Tanjung Priok (Jakarta)", "IDTPP", "Sea", "Jakarta", "Indonesia"),
	("Ho Chi Minh City (Cat Lai)", "VNSGN", "Sea", "Ho Chi Minh City", "Vietnam"),
	("Laem Chabang", "THLCH", "Sea", "Laem Chabang", "Thailand"),
	("Manila", "PHMNL", "Sea", "Manila", "Philippines"),
	("Colombo", "LKCMB", "Sea", "Colombo", "Sri Lanka"),
	("Chattogram (Chittagong)", "BDCGP", "Sea", "Chattogram", "Bangladesh"),
	("Dhaka Air Cargo", "BDDAC", "Air", "Dhaka", "Bangladesh"),
	("Karachi", "PKKHI", "Sea", "Karachi", "Pakistan"),
	("Tashkent Air Cargo", "UZTAS", "Air", "Tashkent", "Uzbekistan"),
	("Almaty Air Cargo", "KZALA", "Air", "Almaty", "Kazakhstan"),
]
