# Copyright (c) 2026 Rishi Mule. All Rights Reserved.
# This code and its associated documentation cannot be copied, modified, or distributed without explicit permission from the author.
"""Bulk data + deterministic generation for dev_seed.py.

Split out so dev_seed.py keeps a curated anchor set while this module carries
the ~10x expansion. All RNG-driven generation uses `_RNG = random.Random(42)`
for reproducibility — seeded counts must stay stable across runs.

Module-level lists are computed once at import time. Order in dev_seed.py is:

    SERVICES   = ANCHOR_SERVICES + EXTRA_SERVICES
    CATEGORIES = ANCHOR_CATEGORIES + EXTRA_CATEGORIES
    ...

Anchor entries keep the existing hand-curated realism (Sharma Store, Priya
Verma's 5 addresses, real product names). Extras add bulk for load-style QA.
"""
from __future__ import annotations

import random
from typing import Any

from app.models.base import UserRole
from app.models.profile import VerificationStatus

_RNG = random.Random(42)


# ---------------------------------------------------------------------------
# EXTRA SERVICES (9 → SERVICES total 12)
# ---------------------------------------------------------------------------
EXTRA_SERVICES: list[dict[str, Any]] = [
    {"slug": "food", "name": "Food & Restaurants", "description": "Prepared meals from cloud kitchens and restaurants"},
    {"slug": "bakery", "name": "Bakery", "description": "Cakes, pastries, breads, and confectionery"},
    {"slug": "meat-seafood", "name": "Meat & Seafood", "description": "Fresh chicken, mutton, fish, and seafood"},
    {"slug": "beauty", "name": "Beauty & Cosmetics", "description": "Makeup, fragrances, and premium skincare"},
    {"slug": "stationery", "name": "Stationery & Books", "description": "School, office stationery, and reading"},
    {"slug": "pet-supplies", "name": "Pet Supplies", "description": "Pet food, accessories, and grooming"},
    {"slug": "home-kitchen", "name": "Home & Kitchen", "description": "Cookware, appliances, decor, and storage"},
    {"slug": "flowers-plants", "name": "Flowers & Plants", "description": "Fresh bouquets, indoor plants, and gardening"},
    {"slug": "sports-fitness", "name": "Sports & Fitness", "description": "Gym equipment, sports gear, and fitness supplements"},
]


# ---------------------------------------------------------------------------
# EXTRA CATEGORIES (91 → CATEGORIES total 100)
# Each entry includes a `brand_pool` used by product generation downstream.
# ---------------------------------------------------------------------------
EXTRA_CATEGORIES: list[dict[str, Any]] = [
    # ----- grocery (7 new; anchor has 3) -----
    {"service_slug": "grocery", "slug": "beverages", "name": "Beverages", "description": "Juices, soft drinks, energy drinks, water",
     "brand_pool": ["Tropicana", "Real", "Minute Maid", "Paper Boat", "Coca-Cola", "Pepsi", "Bisleri", "Red Bull"]},
    {"service_slug": "grocery", "slug": "snacks", "name": "Snacks & Namkeen", "description": "Chips, namkeen, biscuits, mixtures",
     "brand_pool": ["Lays", "Kurkure", "Haldiram's", "Bikaji", "Balaji", "Britannia", "Parle", "Sunfeast"]},
    {"service_slug": "grocery", "slug": "frozen-foods", "name": "Frozen Foods", "description": "Frozen veg, paneer, parathas, kebabs",
     "brand_pool": ["McCain", "Safal", "Sumeru", "ITC Master Chef", "Godrej Yummiez", "Venky's", "Tata Sampann", "Mother's Recipe"]},
    {"service_slug": "grocery", "slug": "breakfast-cereals", "name": "Breakfast & Cereals", "description": "Cornflakes, oats, muesli, jams",
     "brand_pool": ["Kellogg's", "Bagrry's", "Quaker", "Saffola", "Britannia", "MTR", "Nestle", "Yoga Bar"]},
    {"service_slug": "grocery", "slug": "condiments-spices", "name": "Condiments & Spices", "description": "Masalas, sauces, pickles, vinegars",
     "brand_pool": ["MDH", "Everest", "Catch", "Tata Sampann", "MTR", "Kissan", "Maggi", "Veeba"]},
    {"service_slug": "grocery", "slug": "sweets-desserts", "name": "Sweets & Desserts", "description": "Mithai, chocolates, ice creams, kulfi",
     "brand_pool": ["Cadbury", "Nestle", "Amul", "Vadilal", "Kwality Walls", "Hershey's", "Ferrero", "Haldiram's"]},
    {"service_slug": "grocery", "slug": "ready-to-eat", "name": "Ready-to-Eat", "description": "Instant meals, ready gravies, instant mixes",
     "brand_pool": ["MTR", "Haldiram's", "Gits", "ITC Kitchens of India", "Tasty Bite", "Saffola", "Knorr", "Maggi"]},
    # ----- electronics (7 new; anchor has 3) -----
    {"service_slug": "electronics", "slug": "cameras", "name": "Cameras", "description": "DSLRs, mirrorless, action cams",
     "brand_pool": ["Sony", "Canon", "Nikon", "Fujifilm", "GoPro", "DJI", "Panasonic", "Olympus"]},
    {"service_slug": "electronics", "slug": "gaming", "name": "Gaming & Consoles", "description": "Consoles, controllers, gaming gear",
     "brand_pool": ["Sony", "Microsoft", "Nintendo", "Logitech", "Razer", "ASUS ROG", "HyperX", "SteelSeries"]},
    {"service_slug": "electronics", "slug": "tv-entertainment", "name": "TV & Entertainment", "description": "Smart TVs, projectors, soundbars",
     "brand_pool": ["Samsung", "LG", "Sony", "TCL", "Mi", "OnePlus", "Hisense", "BenQ"]},
    {"service_slug": "electronics", "slug": "computer-accessories", "name": "Computer Accessories", "description": "Keyboards, mice, monitors, hubs",
     "brand_pool": ["Logitech", "Dell", "HP", "Microsoft", "Razer", "Keychron", "Lenovo", "Anker"]},
    {"service_slug": "electronics", "slug": "smart-home", "name": "Smart Home", "description": "Smart bulbs, plugs, cameras, locks",
     "brand_pool": ["Mi", "Philips Hue", "TP-Link Kasa", "Wipro Smart", "Syska Smart", "Amazon", "Google", "Realme TechLife"]},
    {"service_slug": "electronics", "slug": "networking", "name": "Networking", "description": "Routers, range extenders, mesh systems",
     "brand_pool": ["TP-Link", "Netgear", "ASUS", "D-Link", "Tenda", "Mi", "Linksys", "Mercusys"]},
    {"service_slug": "electronics", "slug": "kitchen-electronics", "name": "Kitchen Electronics", "description": "Mixers, OTGs, microwaves, kettles",
     "brand_pool": ["Prestige", "Bajaj", "Philips", "Morphy Richards", "Inalsa", "Crompton", "Havells", "Wonderchef"]},
    # ----- pharmacy (7 new; anchor has 3) -----
    {"service_slug": "pharmacy", "slug": "baby-care", "name": "Baby Care", "description": "Diapers, baby food, bath, skincare",
     "brand_pool": ["Pampers", "Huggies", "Mamy Poko", "Johnson's Baby", "Himalaya Baby", "Mamaearth", "Cetaphil Baby", "Sebamed"]},
    {"service_slug": "pharmacy", "slug": "womens-health", "name": "Women's Health", "description": "Feminine hygiene, supplements, intimate care",
     "brand_pool": ["Whisper", "Stayfree", "Sofy", "Carefree", "Pee Safe", "VWash", "Niine", "Sirona"]},
    {"service_slug": "pharmacy", "slug": "mens-grooming", "name": "Men's Grooming", "description": "Razors, shaving, deodorants, beard care",
     "brand_pool": ["Gillette", "Old Spice", "Nivea Men", "Beardo", "Bombay Shaving Co", "The Man Company", "Park Avenue", "Axe"]},
    {"service_slug": "pharmacy", "slug": "ayurveda", "name": "Ayurveda", "description": "Classical and proprietary ayurvedic medicines",
     "brand_pool": ["Patanjali", "Dabur", "Himalaya", "Baidyanath", "Zandu", "Kerala Ayurveda", "Kapiva", "Vicco"]},
    {"service_slug": "pharmacy", "slug": "first-aid", "name": "First Aid", "description": "Bandages, antiseptics, thermometers",
     "brand_pool": ["Dettol", "Savlon", "Band-Aid", "Soframycin", "Burnol", "Hansaplast", "Romsons", "Smith & Nephew"]},
    {"service_slug": "pharmacy", "slug": "medical-devices", "name": "Medical Devices", "description": "BP monitors, glucometers, nebulizers",
     "brand_pool": ["Omron", "Dr Morepen", "Accu-Chek", "OneTouch", "Beurer", "Philips", "Hicks", "Easycare"]},
    {"service_slug": "pharmacy", "slug": "eye-ear-care", "name": "Eye & Ear Care", "description": "Eye drops, contact solutions, ear care",
     "brand_pool": ["Refresh Tears", "Itone", "Systane", "I-Kare", "Bausch + Lomb", "Otrivin Ear", "Waxsol", "Optrex"]},
    # ----- food (8 new) -----
    {"service_slug": "food", "slug": "north-indian", "name": "North Indian", "description": "Rajma, dal makhani, paneer dishes, breads",
     "brand_pool": ["Punjab Grill", "Kake Da Hotel", "Dilli 32", "Sagar Ratna", "Pind Balluchi", "Moti Mahal", "Bukhara Express", "Karim's"]},
    {"service_slug": "food", "slug": "south-indian", "name": "South Indian", "description": "Dosa, idli, sambhar, filter coffee",
     "brand_pool": ["Saravana Bhavan", "Adyar Ananda Bhavan", "Sangeetha", "Murugan Idli", "MTR", "Vasudev Adigas", "Anjappar", "Hotel Empire"]},
    {"service_slug": "food", "slug": "chinese", "name": "Chinese & Asian", "description": "Hakka noodles, manchurian, momos, sushi",
     "brand_pool": ["Mainland China", "Yauatcha", "Berco's", "Hong Kong Eatery", "Chowman", "Wow Momo", "Chings", "Wokyo"]},
    {"service_slug": "food", "slug": "italian-pizza", "name": "Italian & Pizza", "description": "Pizza, pasta, lasagna, garlic bread",
     "brand_pool": ["Dominos", "Pizza Hut", "La Pino'z", "Oven Story", "Smokin Joe's", "California Pizza Kitchen", "Sbarro", "Papa John's"]},
    {"service_slug": "food", "slug": "fast-food", "name": "Fast Food & Burgers", "description": "Burgers, wraps, fries, sandwiches",
     "brand_pool": ["McDonald's", "Burger King", "KFC", "Subway", "Wendy's", "Carl's Jr", "Wat-A-Burger", "Biggies Burger"]},
    {"service_slug": "food", "slug": "biryani-rice", "name": "Biryani & Rice", "description": "Hyderabadi, Lucknowi, dum biryanis, pulao",
     "brand_pool": ["Behrouz", "Paradise", "Biryani Blues", "Faasos Biryani", "Tunday Kababi", "Mehfil", "Bawarchi", "Biryani by Kilo"]},
    {"service_slug": "food", "slug": "desserts-sweets", "name": "Desserts & Mithai", "description": "Cakes, kulfi, gulab jamun, mithai trays",
     "brand_pool": ["Bikanervala", "Haldiram's", "Theobroma", "Cake Box", "Baskin Robbins", "Naturals", "Hangyo", "Cremica"]},
    {"service_slug": "food", "slug": "beverages-juices", "name": "Beverages & Juices", "description": "Fresh juices, mocktails, shakes, smoothies",
     "brand_pool": ["Keventers", "Boost Juice", "Cafe Coffee Day", "Starbucks", "Chaayos", "Chai Point", "Blue Tokai", "Tea Trails"]},
    # ----- bakery (8 new) -----
    {"service_slug": "bakery", "slug": "cakes", "name": "Cakes", "description": "Birthday, wedding, designer cakes",
     "brand_pool": ["Monginis", "Theobroma", "Cake Box", "Ribbons & Balloons", "Hangyo", "Hyatt Bakery", "Brownie Heaven", "FB Cakes"]},
    {"service_slug": "bakery", "slug": "pastries", "name": "Pastries & Slices", "description": "Choco truffle, blackforest, fresh cream",
     "brand_pool": ["Theobroma", "Brownie Heaven", "Monginis", "Birdy's", "Cake Box", "L'Opera", "Truffles", "Au Bon Pain"]},
    {"service_slug": "bakery", "slug": "cookies-biscuits", "name": "Cookies & Biscuits", "description": "Butter cookies, choco-chip, brownies",
     "brand_pool": ["Britannia", "Parle", "Sunfeast", "Unibic", "Anmol", "Karachi Bakery", "Cookieman", "McVitie's"]},
    {"service_slug": "bakery", "slug": "breads-rolls", "name": "Artisan Breads", "description": "Sourdough, focaccia, baguettes, rolls",
     "brand_pool": ["The Baker's Dozen", "Theobroma", "L'Opera", "Sweetish House Mafia", "Au Bon Pain", "Foodhall", "Roastery Bakehouse", "Le Pain Quotidien"]},
    {"service_slug": "bakery", "slug": "savouries-puffs", "name": "Savoury Bakes", "description": "Veg puffs, khari, sandwiches",
     "brand_pool": ["Monginis", "Ribbons & Balloons", "Modern Bakery", "Iyengar's", "Hyatt Bakery", "Theobroma", "L'Opera", "Faasos"]},
    {"service_slug": "bakery", "slug": "donuts", "name": "Donuts", "description": "Glazed, ring, filled donuts",
     "brand_pool": ["Dunkin", "Mad Over Donuts", "Krispy Kreme", "Theobroma", "The Donut Baker", "Baskin Donuts", "DD Donuts", "Donut Baker"]},
    {"service_slug": "bakery", "slug": "breakfast-bakes", "name": "Breakfast Bakes", "description": "Croissants, danishes, muffins, scones",
     "brand_pool": ["Theobroma", "L'Opera", "Au Bon Pain", "Foodhall", "Cinnabon", "Le Pain Quotidien", "Baker Street", "The Baker's Dozen"]},
    {"service_slug": "bakery", "slug": "festive-cakes", "name": "Festive & Special", "description": "Plum cake, fruit cake, designer hampers",
     "brand_pool": ["Monginis", "Theobroma", "Karachi Bakery", "Britannia", "Mio Amore", "Ribbons & Balloons", "Hyatt Bakery", "Cake Box"]},
    # ----- meat-seafood (8 new) -----
    {"service_slug": "meat-seafood", "slug": "chicken", "name": "Chicken", "description": "Whole, curry-cut, boneless, mince",
     "brand_pool": ["Licious", "FreshToHome", "ZappFresh", "Meatigo", "Tata Sampann", "Venky's", "TenderCuts", "Sumeru"]},
    {"service_slug": "meat-seafood", "slug": "mutton", "name": "Mutton", "description": "Curry-cut, biryani-cut, mince, chops",
     "brand_pool": ["Licious", "FreshToHome", "Meatigo", "ZappFresh", "TenderCuts", "Easy Meat", "Just Non Veg", "ChickenCart"]},
    {"service_slug": "meat-seafood", "slug": "fish", "name": "Fish", "description": "Rohu, pomfret, surmai, basa fillets",
     "brand_pool": ["Licious", "FreshToHome", "Captain Fresh", "Sumeru", "Meatigo", "ZappFresh", "Coastal Fresh", "Sea Foods Direct"]},
    {"service_slug": "meat-seafood", "slug": "prawns-shellfish", "name": "Prawns & Shellfish", "description": "Prawns, crab, lobster, squid",
     "brand_pool": ["Licious", "FreshToHome", "Captain Fresh", "Coastal Fresh", "Sumeru", "Meatigo", "ZappFresh", "Sea Foods Direct"]},
    {"service_slug": "meat-seafood", "slug": "eggs", "name": "Eggs", "description": "White, brown, free-range, country",
     "brand_pool": ["Suguna", "Eggoz", "Keggs", "Happy Eggs", "Henfruit", "Indian Eggs Co", "Country Eggs", "Daily Eggs"]},
    {"service_slug": "meat-seafood", "slug": "processed-meats", "name": "Processed & Cold Cuts", "description": "Salami, sausages, bacon, ham",
     "brand_pool": ["Licious", "Meatigo", "ZappFresh", "Venky's", "Prasuma", "Sumeru", "Sausage Co", "FreshToHome"]},
    {"service_slug": "meat-seafood", "slug": "marinated-cuts", "name": "Marinated & Ready-to-Cook", "description": "Marinated kababs, tikkas, biryani kits",
     "brand_pool": ["Licious", "ZappFresh", "Meatigo", "FreshToHome", "TenderCuts", "Sumeru", "Easy Meat", "Just Non Veg"]},
    {"service_slug": "meat-seafood", "slug": "exotic-meats", "name": "Exotic & Imported", "description": "Lamb, turkey, duck, exotic seafood",
     "brand_pool": ["Meatigo", "Licious", "FreshToHome", "Captain Fresh", "Prasuma", "Sumeru", "ZappFresh", "TenderCuts"]},
    # ----- beauty (10 new) -----
    {"service_slug": "beauty", "slug": "makeup", "name": "Makeup", "description": "Lipsticks, foundation, eyeliners, eyeshadows",
     "brand_pool": ["Lakme", "Maybelline", "L'Oreal Paris", "MAC", "Nykaa Cosmetics", "Sugar", "Faces Canada", "Colorbar"]},
    {"service_slug": "beauty", "slug": "fragrances", "name": "Fragrances", "description": "Perfumes, eau de toilette, body mists",
     "brand_pool": ["Calvin Klein", "Hugo Boss", "Davidoff", "Engage", "Wild Stone", "Park Avenue", "Skinn", "Fogg"]},
    {"service_slug": "beauty", "slug": "premium-skincare", "name": "Premium Skincare", "description": "Serums, retinol, vitamin C, sunscreens",
     "brand_pool": ["The Ordinary", "Minimalist", "Dot & Key", "Plum", "The Derma Co", "Re'equil", "Olay", "Neutrogena"]},
    {"service_slug": "beauty", "slug": "mens-skincare", "name": "Men's Skincare", "description": "Face wash, beard oils, moisturisers",
     "brand_pool": ["Beardo", "Bombay Shaving Co", "The Man Company", "Ustraa", "Nivea Men", "Park Avenue", "Garnier Men", "L'Oreal Men"]},
    {"service_slug": "beauty", "slug": "hair-styling", "name": "Hair Styling", "description": "Serums, gels, dyes, styling tools",
     "brand_pool": ["Tresemme", "Schwarzkopf", "Streax", "Garnier", "L'Oreal Professionel", "Set Wet", "Brylcreem", "Wella"]},
    {"service_slug": "beauty", "slug": "nail-care", "name": "Nail Care", "description": "Nail paints, removers, files, kits",
     "brand_pool": ["Lakme", "Maybelline", "Faces Canada", "Sugar", "Colorbar", "Nykaa", "Elle 18", "Insight"]},
    {"service_slug": "beauty", "slug": "bath-body", "name": "Bath & Body", "description": "Shower gels, scrubs, body lotions",
     "brand_pool": ["Dove", "The Body Shop", "Forest Essentials", "Plum", "Mamaearth", "Bath & Body Works", "Nivea", "Khadi"]},
    {"service_slug": "beauty", "slug": "ethnic-bridal", "name": "Ethnic & Bridal", "description": "Henna, kumkum, bindi, kajal, bridal kits",
     "brand_pool": ["Shahnaz Husain", "VLCC", "Lotus Herbals", "Forest Essentials", "Biotique", "Kama Ayurveda", "Just Herbs", "Khadi"]},
    {"service_slug": "beauty", "slug": "mom-baby-beauty", "name": "Mom & Baby Beauty", "description": "Stretch mark creams, baby massage oils",
     "brand_pool": ["Mamaearth", "The Moms Co", "Mother Sparsh", "Sebamed", "Himalaya Baby", "Aveeno Baby", "Earth Mama", "Bella Baby"]},
    {"service_slug": "beauty", "slug": "dermatologist", "name": "Dermatologist Care", "description": "Acne treatment, anti-ageing, brightening",
     "brand_pool": ["La Roche-Posay", "Cetaphil", "Avene", "CeraVe", "Bioderma", "Eucerin", "Vichy", "Neutrogena Derm"]},
    # ----- stationery (10 new) -----
    {"service_slug": "stationery", "slug": "notebooks", "name": "Notebooks & Diaries", "description": "Spiral, ruled, plain, journals",
     "brand_pool": ["Classmate", "Navneet", "Solo", "Sundaram", "Camlin", "Doms", "Faber-Castell", "Pukka Pad"]},
    {"service_slug": "stationery", "slug": "pens-pencils", "name": "Pens & Pencils", "description": "Ballpens, gel pens, sketch pencils",
     "brand_pool": ["Reynolds", "Cello", "Linc", "Pilot", "Faber-Castell", "Apsara", "Natraj", "Parker"]},
    {"service_slug": "stationery", "slug": "school-bags", "name": "School Bags", "description": "Backpacks, lunch bags, water bottles",
     "brand_pool": ["Skybags", "American Tourister", "Wildcraft", "Safari", "Genie", "Tinytotz", "Disney", "Smily Kiddos"]},
    {"service_slug": "stationery", "slug": "art-supplies", "name": "Art & Craft", "description": "Colors, sketch pens, canvas, brushes",
     "brand_pool": ["Camlin", "Faber-Castell", "Doms", "Staedtler", "Pidilite Fevicryl", "Mont Marte", "Royal Talens", "Pebeo"]},
    {"service_slug": "stationery", "slug": "office-supplies", "name": "Office Supplies", "description": "Files, folders, staplers, tapes",
     "brand_pool": ["Solo", "Kangaro", "Casio", "Faber-Castell", "Camlin", "Cello", "Worldone", "Pidilite Fevistik"]},
    {"service_slug": "stationery", "slug": "fiction-books", "name": "Fiction Books", "description": "Indian and international fiction",
     "brand_pool": ["Penguin", "HarperCollins", "Rupa", "Hachette", "Bloomsbury", "Westland", "Scholastic", "Vintage"]},
    {"service_slug": "stationery", "slug": "non-fiction", "name": "Non-Fiction & Biography", "description": "Business, memoir, self-help",
     "brand_pool": ["Penguin Random House", "HarperBusiness", "Bloomsbury", "Rupa", "Hachette", "Manjul", "Jaico", "Tata McGraw Hill"]},
    {"service_slug": "stationery", "slug": "textbooks-academic", "name": "Textbooks & Academic", "description": "NCERT, JEE/NEET, school texts",
     "brand_pool": ["NCERT", "Pearson", "Arihant", "MTG", "Disha", "S. Chand", "Oswaal", "Allen"]},
    {"service_slug": "stationery", "slug": "kids-learning", "name": "Kids' Learning", "description": "Activity books, flashcards, story books",
     "brand_pool": ["Tinkle", "Amar Chitra Katha", "Pratham Books", "Scholastic", "Usborne", "DK Kids", "Karadi Tales", "Tara Books"]},
    {"service_slug": "stationery", "slug": "exam-prep", "name": "Exam Preparation", "description": "JEE, NEET, UPSC, banking prep",
     "brand_pool": ["Arihant", "MTG", "Disha", "S. Chand", "Oswaal", "GKP", "Made Easy", "McGraw Hill Education"]},
    # ----- pet-supplies (8 new) -----
    {"service_slug": "pet-supplies", "slug": "dog-food", "name": "Dog Food", "description": "Dry, wet, puppy, senior, treats",
     "brand_pool": ["Pedigree", "Royal Canin", "Drools", "Purina", "Acana", "Hills Science Diet", "Farmina", "Orijen"]},
    {"service_slug": "pet-supplies", "slug": "cat-food", "name": "Cat Food", "description": "Dry, wet, kitten, hairball care",
     "brand_pool": ["Whiskas", "Royal Canin", "Sheba", "Me-O", "Purepet", "Drools", "Purina ONE", "Hills"]},
    {"service_slug": "pet-supplies", "slug": "fish-aquarium", "name": "Fish & Aquarium", "description": "Fish food, filters, lights, decor",
     "brand_pool": ["Taiyo", "Tetra", "Hikari", "Sera", "API", "Yee", "Sobo", "Aquatic Remedies"]},
    {"service_slug": "pet-supplies", "slug": "bird-supplies", "name": "Bird Supplies", "description": "Bird food, cages, perches, toys",
     "brand_pool": ["Vitapol", "Taiyo", "Boltz", "Aviva", "Sun Seed", "Kaytee", "Versele-Laga", "Witte Molen"]},
    {"service_slug": "pet-supplies", "slug": "pet-grooming", "name": "Pet Grooming", "description": "Shampoos, brushes, clippers, paw care",
     "brand_pool": ["Himalaya", "Bayer", "Beaphar", "Wahl", "FOFOS", "Trixie", "Pawsindia", "Tropiclean"]},
    {"service_slug": "pet-supplies", "slug": "pet-toys", "name": "Pet Toys", "description": "Chew toys, balls, plush, fetch",
     "brand_pool": ["Kong", "Trixie", "FOFOS", "Pawsindia", "Goofy Tails", "Beco", "Petsport", "Outward Hound"]},
    {"service_slug": "pet-supplies", "slug": "pet-medicines", "name": "Pet Medicines & Health", "description": "Dewormers, ticks, vitamins",
     "brand_pool": ["Bayer", "Virbac", "Drools Vet", "Petcare", "Himalaya Pet", "Beaphar", "Zydus", "Intas Pet"]},
    {"service_slug": "pet-supplies", "slug": "pet-accessories", "name": "Pet Accessories", "description": "Collars, leashes, bowls, beds",
     "brand_pool": ["Trixie", "FOFOS", "Pawsindia", "Goofy Tails", "Petsport", "Beco", "Petique", "Mr. Peanut's"]},
    # ----- home-kitchen (10 new) -----
    {"service_slug": "home-kitchen", "slug": "cookware", "name": "Cookware", "description": "Pans, kadhais, pressure cookers",
     "brand_pool": ["Prestige", "Hawkins", "Pigeon", "Vinod", "Cello", "Wonderchef", "Stahl", "Borosil"]},
    {"service_slug": "home-kitchen", "slug": "dinnerware", "name": "Dinnerware", "description": "Plates, bowls, dinner sets",
     "brand_pool": ["Corelle", "Borosil", "Cello", "Larah", "Treo", "Clay Craft", "JCPL", "La Opala"]},
    {"service_slug": "home-kitchen", "slug": "storage-containers", "name": "Storage & Containers", "description": "Jars, lunchboxes, storage sets",
     "brand_pool": ["Tupperware", "Milton", "Cello", "Borosil", "Treo", "Signoraware", "Pigeon", "Lock & Lock"]},
    {"service_slug": "home-kitchen", "slug": "small-appliances", "name": "Small Appliances", "description": "Toasters, irons, kettles, fans",
     "brand_pool": ["Philips", "Bajaj", "Havells", "Crompton", "Usha", "Morphy Richards", "Inalsa", "Singer"]},
    {"service_slug": "home-kitchen", "slug": "cleaning", "name": "Cleaning Supplies", "description": "Detergents, mops, brooms, sponges",
     "brand_pool": ["Surf Excel", "Ariel", "Vim", "Harpic", "Lizol", "Domex", "Scotch Brite", "Gala"]},
    {"service_slug": "home-kitchen", "slug": "home-decor", "name": "Home Decor", "description": "Wall art, candles, vases, frames",
     "brand_pool": ["Home Centre", "Fabindia", "Chumbak", "Ellementry", "Nicobar", "Address Home", "Pure Home + Living", "Westside Home"]},
    {"service_slug": "home-kitchen", "slug": "bedding", "name": "Bedding", "description": "Bedsheets, pillows, blankets, comforters",
     "brand_pool": ["Bombay Dyeing", "Spaces", "Trident", "Welspun", "Portico", "D'Decor", "Story@Home", "Solimo"]},
    {"service_slug": "home-kitchen", "slug": "bath-essentials", "name": "Bath Essentials", "description": "Towels, bathmats, shower curtains",
     "brand_pool": ["Bombay Dyeing", "Welspun", "Trident", "Spaces", "Portico", "Maspar", "Solimo", "Amazon Basics"]},
    {"service_slug": "home-kitchen", "slug": "kitchen-tools", "name": "Kitchen Tools", "description": "Knives, peelers, choppers, graters",
     "brand_pool": ["Pigeon", "Prestige", "Wonderchef", "Tupperware", "Ganesh", "Stahl", "Anjali", "Floraware"]},
    {"service_slug": "home-kitchen", "slug": "lighting-fixtures", "name": "Lighting & Fixtures", "description": "Bulbs, lamps, fairy lights",
     "brand_pool": ["Philips", "Wipro", "Havells", "Bajaj", "Syska", "Crompton", "Eveready", "Orient"]},
    # ----- flowers-plants (4 new) -----
    {"service_slug": "flowers-plants", "slug": "bouquets", "name": "Bouquets", "description": "Fresh bouquets, designer arrangements",
     "brand_pool": ["FNP", "Floweraura", "Ferns N Petals", "MyFlowerTree", "Bloomsvilla", "IGP", "Phoolwala", "FlowerAura"]},
    {"service_slug": "flowers-plants", "slug": "indoor-plants", "name": "Indoor Plants", "description": "Succulents, ferns, money plants, bonsai",
     "brand_pool": ["Ugaoo", "Nurserylive", "MyBageecha", "Plantsguru", "Leafy Tales", "Plantica", "Birthright", "Trustbasket"]},
    {"service_slug": "flowers-plants", "slug": "gardening", "name": "Gardening Supplies", "description": "Pots, seeds, soil, fertilizers",
     "brand_pool": ["Trustbasket", "Ugaoo", "Nurserylive", "GrowGreen", "Sungro", "Plantsguru", "Allin Exporters", "MyBageecha"]},
    {"service_slug": "flowers-plants", "slug": "occasion-arrangements", "name": "Occasion Arrangements", "description": "Wedding, anniversary, sympathy",
     "brand_pool": ["FNP", "Ferns N Petals", "Floweraura", "MyFlowerTree", "Bloomsvilla", "IGP", "Phoolwala", "BloomsOnly"]},
    # ----- sports-fitness (4 new) -----
    {"service_slug": "sports-fitness", "slug": "gym-equipment", "name": "Gym Equipment", "description": "Dumbbells, mats, resistance bands",
     "brand_pool": ["Cockatoo", "Boldfit", "Strauss", "AmazonBasics", "Fitkit", "USI", "Body Maxx", "Nivia"]},
    {"service_slug": "sports-fitness", "slug": "sports-gear", "name": "Sports Gear", "description": "Cricket, football, badminton kit",
     "brand_pool": ["SG", "SS", "Yonex", "Nivia", "Cosco", "Vector X", "Li-Ning", "Adidas Sport"]},
    {"service_slug": "sports-fitness", "slug": "fitness-wearables", "name": "Fitness Wearables", "description": "Bands, watches, heart-rate monitors",
     "brand_pool": ["Fitbit", "Garmin", "Polar", "boAt", "Noise", "Amazfit", "Mi Band", "Realme Band"]},
    {"service_slug": "sports-fitness", "slug": "athletic-wear", "name": "Athletic Wear", "description": "Tees, shorts, leggings, shoes",
     "brand_pool": ["Nike", "Adidas", "Puma", "Under Armour", "Reebok", "ASICS", "Decathlon Kalenji", "HRX"]},
]


# ---------------------------------------------------------------------------
# EXTRA SUBCATEGORIES (273 → SUBCATEGORIES total 300; 3 per new category)
# Each entry carries a `noun` + `variants` driving product name generation.
# `price_range` is (low, high) INR for the 5 generated products at this slot.
# ---------------------------------------------------------------------------
EXTRA_SUBCATEGORIES: list[dict[str, Any]] = [
    # --- beverages ---
    {"category_slug": "beverages", "slug": "fruit-juices", "name": "Fruit Juices", "description": "100% juice, mixed fruits, single origin",
     "noun": "Mixed Fruit Juice", "variants": ["1L", "1.75L", "200ml", "750ml", "500ml"], "price_range": (50, 220)},
    {"category_slug": "beverages", "slug": "soft-drinks", "name": "Soft Drinks", "description": "Cola, lemon, orange, sparkling water",
     "noun": "Soft Drink", "variants": ["330ml Can", "1.25L PET", "750ml", "2L Family", "300ml"], "price_range": (20, 110)},
    {"category_slug": "beverages", "slug": "energy-water", "name": "Energy & Bottled Water", "description": "Energy drinks, mineral water, electrolytes",
     "noun": "Energy Drink", "variants": ["250ml Can", "500ml", "1L", "Pack of 4", "350ml"], "price_range": (20, 320)},
    # --- snacks ---
    {"category_slug": "snacks", "slug": "chips", "name": "Chips & Crisps", "description": "Potato chips, kettle, tortilla",
     "noun": "Potato Chips", "variants": ["52g", "78g", "150g", "Party Pack", "30g"], "price_range": (10, 120)},
    {"category_slug": "snacks", "slug": "namkeen", "name": "Namkeen & Mixtures", "description": "Bhujia, sev, mixtures, chivda",
     "noun": "Bhujia Sev", "variants": ["200g", "400g", "1kg", "100g", "Family Pack"], "price_range": (40, 350)},
    {"category_slug": "snacks", "slug": "biscuits-cookies", "name": "Biscuits & Cookies", "description": "Glucose, cream, butter, marie",
     "noun": "Butter Cookies", "variants": ["150g", "300g", "500g", "Family Pack", "75g"], "price_range": (20, 240)},
    # --- frozen-foods ---
    {"category_slug": "frozen-foods", "slug": "frozen-veg", "name": "Frozen Vegetables", "description": "Peas, sweet corn, mixed veg, beans",
     "noun": "Frozen Green Peas", "variants": ["500g", "1kg", "200g", "Pouch", "Pack of 2"], "price_range": (60, 320)},
    {"category_slug": "frozen-foods", "slug": "frozen-snacks", "name": "Frozen Snacks", "description": "Parathas, kebabs, nuggets, samosa",
     "noun": "Aloo Paratha", "variants": ["Pack of 4", "Pack of 6", "300g", "500g", "Family Pack"], "price_range": (80, 420)},
    {"category_slug": "frozen-foods", "slug": "frozen-meals", "name": "Frozen Meals", "description": "Pizzas, paneer dishes, ready bowls",
     "noun": "Frozen Veg Pizza", "variants": ["Single", "Pack of 2", "Family", "Mini Pack", "300g"], "price_range": (120, 520)},
    # --- breakfast-cereals ---
    {"category_slug": "breakfast-cereals", "slug": "cornflakes", "name": "Cornflakes", "description": "Plain, honey, almond, chocolate",
     "noun": "Cornflakes", "variants": ["475g", "875g", "250g", "Family", "1kg"], "price_range": (90, 520)},
    {"category_slug": "breakfast-cereals", "slug": "oats-muesli", "name": "Oats & Muesli", "description": "Rolled oats, masala oats, fruit muesli",
     "noun": "Rolled Oats", "variants": ["500g", "1kg", "200g", "Pouch", "400g"], "price_range": (60, 460)},
    {"category_slug": "breakfast-cereals", "slug": "spreads-jams", "name": "Spreads & Jams", "description": "Peanut butter, jams, chocolate spreads",
     "noun": "Mixed Fruit Jam", "variants": ["200g", "500g", "1kg", "Mini Pack", "340g"], "price_range": (60, 360)},
    # --- condiments-spices ---
    {"category_slug": "condiments-spices", "slug": "masalas", "name": "Masalas & Blends", "description": "Garam masala, biryani, sambar masala",
     "noun": "Garam Masala", "variants": ["50g", "100g", "200g", "500g", "1kg"], "price_range": (30, 480)},
    {"category_slug": "condiments-spices", "slug": "sauces-ketchup", "name": "Sauces & Ketchup", "description": "Tomato, chilli, soy, mayo, pasta",
     "noun": "Tomato Ketchup", "variants": ["200g", "500g", "1kg", "Pouch", "950g"], "price_range": (25, 220)},
    {"category_slug": "condiments-spices", "slug": "pickles-chutneys", "name": "Pickles & Chutneys", "description": "Mango, lime, mixed, garlic chutneys",
     "noun": "Mango Pickle", "variants": ["200g", "400g", "1kg", "Glass Jar", "100g"], "price_range": (40, 320)},
    # --- sweets-desserts ---
    {"category_slug": "sweets-desserts", "slug": "chocolates", "name": "Chocolates", "description": "Dark, milk, white, premium bars",
     "noun": "Milk Chocolate Bar", "variants": ["50g", "100g", "Pack of 3", "Gift Box", "200g"], "price_range": (40, 950)},
    {"category_slug": "sweets-desserts", "slug": "ice-cream", "name": "Ice Cream", "description": "Tubs, cones, sticks, kulfi",
     "noun": "Vanilla Ice Cream", "variants": ["500ml", "1L", "Tub", "Pack of 6 Cones", "750ml"], "price_range": (80, 620)},
    {"category_slug": "sweets-desserts", "slug": "indian-mithai", "name": "Indian Mithai", "description": "Soan papdi, kaju katli, gulab jamun",
     "noun": "Kaju Katli", "variants": ["250g", "500g", "1kg", "Gift Box", "100g"], "price_range": (180, 1450)},
    # --- ready-to-eat ---
    {"category_slug": "ready-to-eat", "slug": "ready-meals", "name": "Ready Meals", "description": "Heat-and-eat dal, sabzi, biryani",
     "noun": "Ready Dal Makhani", "variants": ["285g", "Pack of 2", "Family Pack", "300g", "Single Serve"], "price_range": (80, 380)},
    {"category_slug": "ready-to-eat", "slug": "instant-mixes", "name": "Instant Mixes", "description": "Dosa, idli, gulab jamun, poha mixes",
     "noun": "Instant Dosa Mix", "variants": ["200g", "500g", "1kg", "Pouch", "100g"], "price_range": (40, 320)},
    {"category_slug": "ready-to-eat", "slug": "instant-noodles", "name": "Instant Noodles & Pasta", "description": "2-minute noodles, cup pasta",
     "noun": "Instant Noodles", "variants": ["70g", "Pack of 4", "Pack of 8", "Cup", "560g"], "price_range": (15, 220)},
    # --- cameras ---
    {"category_slug": "cameras", "slug": "dslr", "name": "DSLR Cameras", "description": "Entry-level and prosumer DSLRs",
     "noun": "DSLR Camera Kit", "variants": ["18-55mm Kit", "Body Only", "Twin Lens", "Pro Body", "55-250mm Kit"], "price_range": (35000, 195000)},
    {"category_slug": "cameras", "slug": "mirrorless", "name": "Mirrorless Cameras", "description": "Compact full-frame and APS-C",
     "noun": "Mirrorless Camera", "variants": ["16-50mm Kit", "Body Only", "Twin Lens", "Full Frame", "Vlogger Kit"], "price_range": (45000, 285000)},
    {"category_slug": "cameras", "slug": "action-drone", "name": "Action Cams & Drones", "description": "Action cameras, mini drones",
     "noun": "Action Camera", "variants": ["4K", "5K Hero", "Mini Drone", "Pro Drone", "Combo Kit"], "price_range": (8000, 145000)},
    # --- gaming ---
    {"category_slug": "gaming", "slug": "gaming-consoles", "name": "Gaming Consoles", "description": "PS5, Xbox, Switch, handheld",
     "noun": "Gaming Console", "variants": ["Standard", "Digital Edition", "Pro Bundle", "Handheld", "Disc Edition"], "price_range": (24999, 84999)},
    {"category_slug": "gaming", "slug": "controllers", "name": "Controllers", "description": "Wireless controllers, fight sticks",
     "noun": "Wireless Controller", "variants": ["Standard", "Pro", "Elite", "Mobile Clip", "Charging Dock"], "price_range": (1499, 14999)},
    {"category_slug": "gaming", "slug": "gaming-accessories", "name": "Gaming Accessories", "description": "Headsets, mousepads, racing wheels",
     "noun": "Gaming Headset", "variants": ["Wired", "Wireless", "Pro Tournament", "RGB Edition", "7.1 Surround"], "price_range": (1999, 24999)},
    # --- tv-entertainment ---
    {"category_slug": "tv-entertainment", "slug": "smart-tvs", "name": "Smart TVs", "description": "4K, QLED, OLED, Mini-LED TVs",
     "noun": "4K Smart TV", "variants": ["43-inch", "55-inch", "65-inch", "75-inch", "32-inch"], "price_range": (18999, 184999)},
    {"category_slug": "tv-entertainment", "slug": "soundbars", "name": "Soundbars & Home Theatre", "description": "2.1, 5.1, Dolby Atmos bars",
     "noun": "Soundbar", "variants": ["2.0", "2.1", "5.1 Dolby", "3.1 Atmos", "Subwoofer Combo"], "price_range": (4999, 89990)},
    {"category_slug": "tv-entertainment", "slug": "streaming-devices", "name": "Streaming Devices", "description": "Fire Stick, Chromecast, Apple TV",
     "noun": "Streaming Stick", "variants": ["4K", "FHD", "Pro", "Mini", "Lite"], "price_range": (2999, 18999)},
    # --- computer-accessories ---
    {"category_slug": "computer-accessories", "slug": "keyboards-mice", "name": "Keyboards & Mice", "description": "Mechanical, wireless, gaming",
     "noun": "Wireless Keyboard", "variants": ["Standard", "Mechanical", "RGB Gaming", "Compact 60%", "Ergonomic"], "price_range": (799, 18999)},
    {"category_slug": "computer-accessories", "slug": "monitors", "name": "Monitors", "description": "FHD, QHD, 4K, curved, ultrawide",
     "noun": "Monitor", "variants": ["24-inch FHD", "27-inch QHD", "32-inch 4K", "Ultrawide", "Curved"], "price_range": (8999, 124999)},
    {"category_slug": "computer-accessories", "slug": "docks-hubs", "name": "Docks, Hubs & Storage", "description": "USB hubs, SSDs, HDDs, dongles",
     "noun": "USB-C Hub", "variants": ["7-in-1", "12-in-1", "Compact", "Pro Dock", "Travel Hub"], "price_range": (1299, 24999)},
    # --- smart-home ---
    {"category_slug": "smart-home", "slug": "smart-lighting", "name": "Smart Lighting", "description": "Bulbs, strips, panels",
     "noun": "Smart LED Bulb", "variants": ["9W RGB", "12W White", "Strip 5m", "Pack of 2", "Panel"], "price_range": (399, 9999)},
    {"category_slug": "smart-home", "slug": "smart-plugs-sensors", "name": "Smart Plugs & Sensors", "description": "Plugs, motion, door sensors",
     "noun": "Smart Plug", "variants": ["10A", "16A Heavy Duty", "Sensor Combo", "Pack of 2", "Outdoor"], "price_range": (499, 4999)},
    {"category_slug": "smart-home", "slug": "smart-security", "name": "Smart Security", "description": "Cameras, doorbells, smart locks",
     "noun": "Smart Camera", "variants": ["Indoor 360", "Outdoor", "Doorbell", "Pan-Tilt", "Pro Edition"], "price_range": (1499, 24999)},
    # --- networking ---
    {"category_slug": "networking", "slug": "wifi-routers", "name": "WiFi Routers", "description": "AC, AX, WiFi 6, dual-band",
     "noun": "WiFi Router", "variants": ["AC1200", "AX1800 WiFi 6", "Dual Band", "Mesh Single", "AX5400"], "price_range": (1299, 24999)},
    {"category_slug": "networking", "slug": "range-extenders", "name": "Range Extenders", "description": "WiFi extenders, powerline adapters",
     "noun": "WiFi Range Extender", "variants": ["AC750", "AC1200", "AX1500", "Plug-in", "Outdoor"], "price_range": (1199, 9999)},
    {"category_slug": "networking", "slug": "mesh-systems", "name": "Mesh WiFi Systems", "description": "Whole-home mesh kits",
     "noun": "Mesh WiFi System", "variants": ["2-pack", "3-pack", "AX3000", "AX5400 Pro", "Outdoor Mesh"], "price_range": (5999, 49999)},
    # --- kitchen-electronics ---
    {"category_slug": "kitchen-electronics", "slug": "mixer-grinders", "name": "Mixer Grinders", "description": "Wet/dry mixers, juicers",
     "noun": "Mixer Grinder", "variants": ["500W 3-Jar", "750W 4-Jar", "1000W Pro", "Wet Grinder", "Hand Blender"], "price_range": (1999, 14999)},
    {"category_slug": "kitchen-electronics", "slug": "microwave-otg", "name": "Microwave & OTG", "description": "Convection, solo, grill, OTG",
     "noun": "Convection Microwave", "variants": ["20L", "25L Solo", "30L Convection", "Grill 23L", "OTG 28L"], "price_range": (4999, 28999)},
    {"category_slug": "kitchen-electronics", "slug": "kettles-toasters", "name": "Kettles & Toasters", "description": "Electric kettles, pop-up toasters",
     "noun": "Electric Kettle", "variants": ["1.5L", "1.8L", "2L Steel", "Travel 0.5L", "Pop-up Toaster"], "price_range": (799, 4999)},
    # --- baby-care ---
    {"category_slug": "baby-care", "slug": "diapers", "name": "Diapers & Wipes", "description": "Tape, pant style, wipes",
     "noun": "Baby Diapers", "variants": ["Small 60", "Medium 76", "Large 64", "XL 50", "Wipes 80"], "price_range": (199, 1599)},
    {"category_slug": "baby-care", "slug": "baby-food", "name": "Baby Food", "description": "Cerelac, formula, snacks",
     "noun": "Stage 1 Cereal", "variants": ["300g", "400g Refill", "Stage 2", "Stage 3", "Tin 500g"], "price_range": (150, 1450)},
    {"category_slug": "baby-care", "slug": "baby-bath", "name": "Baby Bath & Skincare", "description": "Baby shampoo, lotion, oil",
     "noun": "Baby Shampoo", "variants": ["100ml", "200ml", "475ml", "Combo", "50ml"], "price_range": (60, 590)},
    # --- womens-health ---
    {"category_slug": "womens-health", "slug": "sanitary-pads", "name": "Sanitary Pads", "description": "Day, night, overnight, ultra-thin",
     "noun": "Sanitary Pads", "variants": ["Regular 30", "XL 14", "Overnight 16", "Ultra Thin 20", "Pack of 3"], "price_range": (140, 980)},
    {"category_slug": "womens-health", "slug": "intimate-wash", "name": "Intimate Hygiene", "description": "Washes, wipes, mists",
     "noun": "Intimate Wash", "variants": ["100ml", "200ml", "Wipes 10", "Foam 150ml", "Mist 50ml"], "price_range": (140, 580)},
    {"category_slug": "womens-health", "slug": "menstrual-cups", "name": "Menstrual Cups & Tampons", "description": "Cups, tampons, period panties",
     "noun": "Menstrual Cup", "variants": ["Small", "Medium", "Large", "Twin Pack", "Sterilizer Combo"], "price_range": (299, 1999)},
    # --- mens-grooming ---
    {"category_slug": "mens-grooming", "slug": "razors-shaving", "name": "Razors & Shaving", "description": "Cartridge, disposable, shaving foam",
     "noun": "Shaving Razor", "variants": ["3-Blade", "5-Blade", "Disposable Pack of 5", "Foam 200g", "Gel 245g"], "price_range": (75, 1299)},
    {"category_slug": "mens-grooming", "slug": "beard-care", "name": "Beard Care", "description": "Beard oils, balms, trimmers",
     "noun": "Beard Oil", "variants": ["30ml", "50ml", "Combo Wash+Oil", "Balm 60g", "Trimmer Kit"], "price_range": (199, 2499)},
    {"category_slug": "mens-grooming", "slug": "deodorants-men", "name": "Deodorants for Men", "description": "Sprays, roll-ons, perfumes",
     "noun": "Body Spray", "variants": ["150ml", "220ml", "Twin Pack", "Roll-on 50ml", "Pocket Perfume"], "price_range": (120, 890)},
    # --- ayurveda ---
    {"category_slug": "ayurveda", "slug": "classical-medicines", "name": "Classical Medicines", "description": "Vati, ras, lehyam, arishtam",
     "noun": "Ayurvedic Tablet", "variants": ["60s", "120s", "Bottle", "200g", "450ml Syrup"], "price_range": (80, 980)},
    {"category_slug": "ayurveda", "slug": "ayurvedic-oils", "name": "Ayurvedic Oils", "description": "Hair oils, joint pain, body oils",
     "noun": "Ayurvedic Hair Oil", "variants": ["100ml", "200ml", "500ml", "Pouch", "Combo"], "price_range": (80, 690)},
    {"category_slug": "ayurveda", "slug": "ayurvedic-juices", "name": "Ayurvedic Juices", "description": "Aloe vera, amla, karela juices",
     "noun": "Aloe Vera Juice", "variants": ["500ml", "1L", "Family Pack", "Combo", "200ml"], "price_range": (140, 690)},
    # --- first-aid ---
    {"category_slug": "first-aid", "slug": "bandages-tapes", "name": "Bandages & Tapes", "description": "Plasters, gauze, surgical tape",
     "noun": "First Aid Bandages", "variants": ["Pack of 20", "Pack of 50", "Family Pack", "Waterproof 30", "Roll"], "price_range": (40, 480)},
    {"category_slug": "first-aid", "slug": "antiseptics", "name": "Antiseptics & Disinfectants", "description": "Liquids, sprays, ointments",
     "noun": "Antiseptic Liquid", "variants": ["110ml", "250ml", "550ml", "1L", "5L"], "price_range": (75, 920)},
    {"category_slug": "first-aid", "slug": "thermometers", "name": "Thermometers & Basics", "description": "Digital, infrared, cotton, masks",
     "noun": "Digital Thermometer", "variants": ["Standard", "Flexible Tip", "Infrared Forehead", "Ear Probe", "Combo Kit"], "price_range": (140, 2999)},
    # --- medical-devices ---
    {"category_slug": "medical-devices", "slug": "bp-monitors", "name": "BP Monitors", "description": "Upper arm, wrist BP monitors",
     "noun": "Blood Pressure Monitor", "variants": ["Upper Arm", "Wrist", "Bluetooth", "Pro", "Travel"], "price_range": (1199, 6999)},
    {"category_slug": "medical-devices", "slug": "glucometers", "name": "Glucometers & Strips", "description": "Glucose meters, test strips, lancets",
     "noun": "Glucometer Kit", "variants": ["Starter Kit", "Pro Bluetooth", "50 Strips", "100 Strips", "Lancets 100"], "price_range": (399, 2499)},
    {"category_slug": "medical-devices", "slug": "nebulizers-oximeters", "name": "Nebulizers & Oximeters", "description": "Nebulizers, pulse oximeters, weighing scales",
     "noun": "Pulse Oximeter", "variants": ["Standard", "Pro", "Pediatric", "Bluetooth", "Combo Kit"], "price_range": (599, 4999)},
    # --- eye-ear-care ---
    {"category_slug": "eye-ear-care", "slug": "eye-drops", "name": "Eye Drops & Care", "description": "Lubricants, allergy, redness",
     "noun": "Lubricating Eye Drops", "variants": ["10ml", "15ml", "Twin Pack", "Pack of 3", "30ml"], "price_range": (60, 420)},
    {"category_slug": "eye-ear-care", "slug": "contact-lens-care", "name": "Contact Lens Care", "description": "Solutions, cases, multi-purpose",
     "noun": "Contact Lens Solution", "variants": ["120ml", "240ml", "360ml", "Travel 60ml", "Combo Case"], "price_range": (180, 890)},
    {"category_slug": "eye-ear-care", "slug": "ear-nose-care", "name": "Ear & Nose Care", "description": "Ear drops, wax removers, nasal sprays",
     "noun": "Ear Drops", "variants": ["10ml", "Drops 15ml", "Wax Removal Kit", "Nasal Spray 10ml", "Combo"], "price_range": (70, 420)},
    # --- north-indian ---
    {"category_slug": "north-indian", "slug": "north-indian-curries", "name": "Curries & Mains", "description": "Paneer butter masala, dal makhani, kadhai paneer",
     "noun": "Paneer Butter Masala", "variants": ["Serves 1", "Serves 2", "Family Pack", "Half Plate", "Combo with Naan"], "price_range": (180, 720)},
    {"category_slug": "north-indian", "slug": "north-indian-breads", "name": "Breads & Rotis", "description": "Naan, kulcha, paratha, missi roti",
     "noun": "Butter Naan", "variants": ["Single", "Pack of 4", "Pack of 6", "Stuffed Single", "Family Pack"], "price_range": (40, 360)},
    {"category_slug": "north-indian", "slug": "north-indian-starters", "name": "Starters & Tandoor", "description": "Tikka, kabab, tandoori",
     "noun": "Paneer Tikka", "variants": ["6 pcs", "8 pcs", "Family Plate", "Half", "Sharing Platter"], "price_range": (180, 920)},
    # --- south-indian ---
    {"category_slug": "south-indian", "slug": "dosa-uttapam", "name": "Dosa & Uttapam", "description": "Masala, plain, paper, set dosa",
     "noun": "Masala Dosa", "variants": ["Single", "Set of 2", "Family Pack", "Mini 4 pcs", "Cheese"], "price_range": (90, 380)},
    {"category_slug": "south-indian", "slug": "idli-vada", "name": "Idli & Vada", "description": "Plate, family pack, mini-idlis",
     "noun": "Idli", "variants": ["Plate of 4", "Plate of 6", "Family 12", "Mini 20", "Combo with Vada"], "price_range": (60, 340)},
    {"category_slug": "south-indian", "slug": "south-indian-meals", "name": "South Indian Meals", "description": "Thali, biryani, sambar rice",
     "noun": "South Indian Thali", "variants": ["Regular", "Special", "Family", "Half", "Mini"], "price_range": (180, 720)},
    # --- chinese ---
    {"category_slug": "chinese", "slug": "chinese-noodles", "name": "Noodles", "description": "Hakka, schezwan, chilli garlic noodles",
     "noun": "Hakka Noodles", "variants": ["Half", "Full", "Family Pack", "Combo Manchurian", "Single"], "price_range": (120, 480)},
    {"category_slug": "chinese", "slug": "chinese-rice", "name": "Fried Rice & Gravies", "description": "Veg fried rice, manchurian, hot garlic",
     "noun": "Veg Fried Rice", "variants": ["Half", "Full", "Family", "Combo Gravy", "Single"], "price_range": (130, 520)},
    {"category_slug": "chinese", "slug": "momos-dimsum", "name": "Momos & Dimsum", "description": "Steamed, fried, pan-fried, tandoori momos",
     "noun": "Veg Momos", "variants": ["6 pcs", "10 pcs", "Family 20", "Pan Fried 8", "Tandoori 8"], "price_range": (80, 480)},
    # --- italian-pizza ---
    {"category_slug": "italian-pizza", "slug": "pizzas", "name": "Pizzas", "description": "Margherita, pepperoni, deluxe, cheese burst",
     "noun": "Margherita Pizza", "variants": ["Regular 7-inch", "Medium 10-inch", "Large 12-inch", "Personal Size", "Family 14-inch"], "price_range": (180, 1280)},
    {"category_slug": "italian-pizza", "slug": "pasta-lasagna", "name": "Pasta & Lasagna", "description": "Penne, spaghetti, fettuccine, lasagna",
     "noun": "Penne Alfredo", "variants": ["Regular", "Large", "Family", "Half Plate", "Combo Bread"], "price_range": (180, 720)},
    {"category_slug": "italian-pizza", "slug": "garlic-bread-sides", "name": "Sides & Garlic Bread", "description": "Garlic bread, dips, salads, wings",
     "noun": "Stuffed Garlic Bread", "variants": ["Regular", "Cheesy", "Family", "Combo Dips", "Mini"], "price_range": (90, 380)},
    # --- fast-food ---
    {"category_slug": "fast-food", "slug": "burgers", "name": "Burgers", "description": "Veg, chicken, paneer, double patty",
     "noun": "Veggie Burger", "variants": ["Regular", "Double", "Family Combo", "King Size", "Mini"], "price_range": (60, 480)},
    {"category_slug": "fast-food", "slug": "wraps-rolls", "name": "Wraps & Rolls", "description": "Kathi, frankie, shawarma, paneer wrap",
     "noun": "Paneer Kathi Roll", "variants": ["Single", "Twin Pack", "Family Combo", "Mini", "Sharing"], "price_range": (90, 380)},
    {"category_slug": "fast-food", "slug": "fries-sides", "name": "Fries & Sides", "description": "Fries, nuggets, wedges, onion rings",
     "noun": "French Fries", "variants": ["Small", "Medium", "Large", "Family", "Combo Dip"], "price_range": (60, 280)},
    # --- biryani-rice ---
    {"category_slug": "biryani-rice", "slug": "veg-biryani", "name": "Veg Biryani", "description": "Hyderabadi veg, paneer, mushroom biryani",
     "noun": "Hyderabadi Veg Biryani", "variants": ["Single", "Serves 2", "Family Pack", "Mini", "Sharing Bowl"], "price_range": (180, 680)},
    {"category_slug": "biryani-rice", "slug": "non-veg-biryani", "name": "Non-Veg Biryani", "description": "Chicken, mutton, prawn biryani",
     "noun": "Chicken Dum Biryani", "variants": ["Single", "Serves 2", "Family", "Half Plate", "Sharing Bowl"], "price_range": (220, 920)},
    {"category_slug": "biryani-rice", "slug": "pulao-rice", "name": "Pulao & Rice", "description": "Veg pulao, jeera rice, lemon rice",
     "noun": "Veg Pulao", "variants": ["Single", "Family", "Combo Raita", "Mini", "Sharing Bowl"], "price_range": (140, 480)},
    # --- desserts-sweets (food service) ---
    {"category_slug": "desserts-sweets", "slug": "cakes-pastries-food", "name": "Cakes & Pastries", "description": "Chocolate, red velvet, fresh cream",
     "noun": "Chocolate Cake Slice", "variants": ["Slice", "500g", "1kg", "Mini Cup", "Birthday 1kg"], "price_range": (90, 1280)},
    {"category_slug": "desserts-sweets", "slug": "indian-sweets-food", "name": "Indian Sweets", "description": "Gulab jamun, jalebi, rasgulla",
     "noun": "Gulab Jamun", "variants": ["4 pcs", "8 pcs", "Family 12 pcs", "Tin 1kg", "Box of 6"], "price_range": (80, 720)},
    {"category_slug": "desserts-sweets", "slug": "ice-cream-food", "name": "Ice Cream & Frozen", "description": "Scoops, sundaes, kulfi, falooda",
     "noun": "Chocolate Sundae", "variants": ["Single Scoop", "Double", "Family Sundae", "Cone", "Falooda"], "price_range": (80, 480)},
    # --- beverages-juices (food service) ---
    {"category_slug": "beverages-juices", "slug": "fresh-juices-food", "name": "Fresh Juices", "description": "Orange, watermelon, mosambi, mixed",
     "noun": "Orange Juice", "variants": ["250ml", "500ml", "1L", "Family Pitcher", "Mini Glass"], "price_range": (60, 380)},
    {"category_slug": "beverages-juices", "slug": "shakes-smoothies", "name": "Shakes & Smoothies", "description": "Banana, oreo, cold coffee, smoothies",
     "noun": "Cold Coffee Shake", "variants": ["Regular", "Large", "Family Jar", "Mini", "Combo"], "price_range": (90, 380)},
    {"category_slug": "beverages-juices", "slug": "tea-coffee-food", "name": "Tea & Coffee", "description": "Masala chai, filter coffee, latte",
     "noun": "Masala Chai", "variants": ["Cup", "Glass", "Pot of 2", "Family Kettle", "Iced"], "price_range": (30, 280)},
    # --- cakes (bakery) ---
    {"category_slug": "cakes", "slug": "chocolate-cakes", "name": "Chocolate Cakes", "description": "Choco truffle, dark, dutch, fudge",
     "noun": "Chocolate Truffle Cake", "variants": ["500g", "1kg", "2kg", "Heart Shape 1kg", "Birthday 1.5kg"], "price_range": (450, 2980)},
    {"category_slug": "cakes", "slug": "fresh-cream-cakes", "name": "Fresh Cream Cakes", "description": "Black forest, pineapple, butterscotch",
     "noun": "Black Forest Cake", "variants": ["500g", "1kg", "2kg", "Half kg", "1.5kg"], "price_range": (380, 2680)},
    {"category_slug": "cakes", "slug": "designer-cakes", "name": "Designer & Photo Cakes", "description": "Custom, photo print, fondant, kid",
     "noun": "Photo Print Cake", "variants": ["1kg", "1.5kg", "2kg", "Custom 500g", "Designer 3kg"], "price_range": (650, 4980)},
    # --- pastries (bakery) ---
    {"category_slug": "pastries", "slug": "choco-pastries", "name": "Chocolate Pastries", "description": "Choco truffle slice, dark choc",
     "noun": "Chocolate Pastry", "variants": ["Single", "Pack of 4", "Pack of 6", "Pack of 12", "Box of 2"], "price_range": (80, 760)},
    {"category_slug": "pastries", "slug": "fruit-pastries", "name": "Fruit Pastries", "description": "Strawberry, mango, pineapple slices",
     "noun": "Strawberry Pastry", "variants": ["Single", "Pack of 4", "Pack of 6", "Pack of 12", "Box of 2"], "price_range": (80, 760)},
    {"category_slug": "pastries", "slug": "premium-pastries", "name": "Premium Pastries", "description": "Eclairs, opera, tiramisu, mousse",
     "noun": "Tiramisu Cup", "variants": ["Single", "Pack of 2", "Pack of 4", "Pack of 6", "Sharing Box"], "price_range": (140, 980)},
    # --- cookies-biscuits ---
    {"category_slug": "cookies-biscuits", "slug": "butter-cookies", "name": "Butter Cookies", "description": "Danish, butter, shortbread",
     "noun": "Danish Butter Cookies", "variants": ["200g", "400g", "Tin 700g", "Pouch 150g", "Gift Box"], "price_range": (90, 980)},
    {"category_slug": "cookies-biscuits", "slug": "chocolate-cookies", "name": "Chocolate Cookies", "description": "Choco chip, choco brownie, dark",
     "noun": "Chocolate Chip Cookies", "variants": ["150g", "300g", "Family 500g", "Mini Pack 75g", "Combo"], "price_range": (40, 580)},
    {"category_slug": "cookies-biscuits", "slug": "brownies-bars", "name": "Brownies & Bars", "description": "Walnut brownies, fudge bars, granola",
     "noun": "Walnut Brownie", "variants": ["Single", "Pack of 4", "Pack of 6", "Family 12", "Box of 2"], "price_range": (60, 720)},
    # --- breads-rolls (artisan) ---
    {"category_slug": "breads-rolls", "slug": "sourdough-breads", "name": "Sourdough Breads", "description": "Classic, multigrain, olive sourdough",
     "noun": "Classic Sourdough Loaf", "variants": ["400g", "600g", "800g", "Half Loaf", "Sharing"], "price_range": (220, 680)},
    {"category_slug": "breads-rolls", "slug": "focaccia-baguettes", "name": "Focaccia & Baguettes", "description": "Rosemary focaccia, baguettes",
     "noun": "Rosemary Focaccia", "variants": ["Single", "Family Tray", "Cocktail", "Half", "Pack of 2"], "price_range": (180, 580)},
    {"category_slug": "breads-rolls", "slug": "specialty-rolls", "name": "Specialty Rolls", "description": "Croissants, ciabatta, brioche",
     "noun": "Butter Croissant", "variants": ["Single", "Pack of 4", "Pack of 6", "Family", "Mini Pack"], "price_range": (90, 580)},
    # --- savouries-puffs ---
    {"category_slug": "savouries-puffs", "slug": "veg-puffs", "name": "Veg Puffs & Patties", "description": "Aloo, paneer, mushroom puffs",
     "noun": "Veg Puff", "variants": ["Single", "Pack of 4", "Pack of 6", "Family 12", "Mini 8"], "price_range": (30, 320)},
    {"category_slug": "savouries-puffs", "slug": "khari-toast", "name": "Khari & Toast", "description": "Butter khari, jeera toast, masala",
     "noun": "Butter Khari", "variants": ["200g", "400g", "1kg", "Family 600g", "Pouch 100g"], "price_range": (40, 380)},
    {"category_slug": "savouries-puffs", "slug": "savoury-sandwiches", "name": "Sandwiches", "description": "Veg, club, grilled, chicken sandwich",
     "noun": "Veg Club Sandwich", "variants": ["Single", "Pack of 2", "Family", "Mini Pack of 4", "Sharing"], "price_range": (90, 480)},
    # --- donuts ---
    {"category_slug": "donuts", "slug": "glazed-donuts", "name": "Glazed Donuts", "description": "Classic glazed, vanilla, strawberry",
     "noun": "Glazed Donut", "variants": ["Single", "Pack of 4", "Pack of 6", "Pack of 12", "Box of 2"], "price_range": (70, 720)},
    {"category_slug": "donuts", "slug": "filled-donuts", "name": "Filled Donuts", "description": "Chocolate, custard, nutella filled",
     "noun": "Chocolate Filled Donut", "variants": ["Single", "Pack of 4", "Pack of 6", "Pack of 12", "Box of 2"], "price_range": (90, 880)},
    {"category_slug": "donuts", "slug": "premium-donuts", "name": "Premium Donuts", "description": "Designer, themed, cake donuts",
     "noun": "Designer Donut", "variants": ["Single", "Pack of 4", "Pack of 6", "Themed Box", "Gift Pack"], "price_range": (120, 1280)},
    # --- breakfast-bakes ---
    {"category_slug": "breakfast-bakes", "slug": "croissants-danish", "name": "Croissants & Danish", "description": "Butter, chocolate, almond croissants",
     "noun": "Almond Croissant", "variants": ["Single", "Pack of 4", "Pack of 6", "Pack of 12", "Box of 2"], "price_range": (90, 720)},
    {"category_slug": "breakfast-bakes", "slug": "muffins-scones", "name": "Muffins & Scones", "description": "Blueberry, choco, banana muffins",
     "noun": "Blueberry Muffin", "variants": ["Single", "Pack of 4", "Pack of 6", "Pack of 12", "Box of 2"], "price_range": (70, 580)},
    {"category_slug": "breakfast-bakes", "slug": "cinnamon-rolls", "name": "Cinnamon & Sweet Rolls", "description": "Cinnamon rolls, sticky buns",
     "noun": "Cinnamon Roll", "variants": ["Single", "Pack of 2", "Pack of 4", "Family Box", "Sharing"], "price_range": (120, 680)},
    # --- festive-cakes ---
    {"category_slug": "festive-cakes", "slug": "plum-fruit-cakes", "name": "Plum & Fruit Cakes", "description": "Traditional plum, rum-soaked, fruit",
     "noun": "Rich Plum Cake", "variants": ["500g", "1kg", "2kg", "Tin Box", "Gift Hamper"], "price_range": (380, 2480)},
    {"category_slug": "festive-cakes", "slug": "festive-hampers", "name": "Festive Hampers", "description": "Christmas, Diwali, anniversary hampers",
     "noun": "Festive Hamper", "variants": ["Mini", "Standard", "Premium", "Deluxe", "Corporate"], "price_range": (980, 6480)},
    {"category_slug": "festive-cakes", "slug": "tier-celebration-cakes", "name": "Tier & Celebration Cakes", "description": "Two-tier, three-tier wedding",
     "noun": "Two-Tier Celebration Cake", "variants": ["2kg", "3kg", "5kg Wedding", "Designer 2kg", "Custom 4kg"], "price_range": (1480, 12980)},
    # --- chicken (meat-seafood) ---
    {"category_slug": "chicken", "slug": "whole-chicken", "name": "Whole Chicken", "description": "Cleaned, skinless, with skin",
     "noun": "Whole Chicken", "variants": ["750g", "1kg", "1.2kg Skinless", "1.5kg", "2kg Family"], "price_range": (180, 720)},
    {"category_slug": "chicken", "slug": "chicken-cuts", "name": "Chicken Cuts", "description": "Curry cut, boneless, mince, drumsticks",
     "noun": "Chicken Curry Cut", "variants": ["500g", "1kg", "Boneless 500g", "Mince 500g", "Drumsticks 1kg"], "price_range": (220, 880)},
    {"category_slug": "chicken", "slug": "chicken-ready", "name": "Marinated Chicken", "description": "Tikka, tandoori, kabab marinated",
     "noun": "Chicken Tikka Marinated", "variants": ["250g", "500g", "1kg", "Family Pack", "Mini Pack"], "price_range": (180, 980)},
    # --- mutton ---
    {"category_slug": "mutton", "slug": "mutton-cuts", "name": "Mutton Cuts", "description": "Curry cut, biryani cut, chops",
     "noun": "Mutton Curry Cut", "variants": ["500g", "1kg", "Biryani Cut 1kg", "Mince 500g", "Family Pack"], "price_range": (480, 1880)},
    {"category_slug": "mutton", "slug": "mutton-chops-special", "name": "Chops & Specials", "description": "Chops, sik kababs, sheekh",
     "noun": "Mutton Chops", "variants": ["500g", "1kg", "Sheekh 500g", "Family Pack", "Mini"], "price_range": (580, 1880)},
    {"category_slug": "mutton", "slug": "mutton-marinated", "name": "Marinated Mutton", "description": "Galouti, kebab, biryani-ready",
     "noun": "Galouti Marinated Mutton", "variants": ["500g", "1kg", "Family Pack", "Mini Pack", "Combo Kit"], "price_range": (480, 1980)},
    # --- fish ---
    {"category_slug": "fish", "slug": "freshwater-fish", "name": "Freshwater Fish", "description": "Rohu, katla, basa, tilapia",
     "noun": "Rohu Fish", "variants": ["500g Curry Cut", "1kg", "Steaks 500g", "Whole 1kg", "Family Pack"], "price_range": (180, 880)},
    {"category_slug": "fish", "slug": "seawater-fish", "name": "Seawater Fish", "description": "Pomfret, surmai, rawas, bangda",
     "noun": "Pomfret Fish", "variants": ["500g", "1kg Whole", "Steaks 500g", "Curry Cut 750g", "Family"], "price_range": (380, 1880)},
    {"category_slug": "fish", "slug": "fish-fillets", "name": "Fish Fillets", "description": "Basa, tilapia, salmon fillets",
     "noun": "Basa Fillet", "variants": ["250g", "500g", "1kg", "Pack of 2", "Family Pack"], "price_range": (220, 1480)},
    # --- prawns-shellfish ---
    {"category_slug": "prawns-shellfish", "slug": "prawns", "name": "Prawns", "description": "Small, medium, tiger, jumbo prawns",
     "noun": "Tiger Prawns Medium", "variants": ["250g", "500g", "1kg", "Jumbo 500g", "Family Pack"], "price_range": (280, 1880)},
    {"category_slug": "prawns-shellfish", "slug": "crab-lobster", "name": "Crab & Lobster", "description": "Crab, lobster, langoustines",
     "noun": "Sea Crab", "variants": ["500g", "1kg", "Family Pack", "Lobster 500g", "Crab Meat 250g"], "price_range": (480, 2980)},
    {"category_slug": "prawns-shellfish", "slug": "squid-clams", "name": "Squid & Clams", "description": "Squid rings, clams, mussels, oysters",
     "noun": "Squid Rings", "variants": ["250g", "500g", "1kg", "Clams 500g", "Mussels 500g"], "price_range": (180, 1280)},
    # --- eggs ---
    {"category_slug": "eggs", "slug": "chicken-eggs", "name": "Chicken Eggs", "description": "White, brown, free-range",
     "noun": "Farm Fresh Eggs", "variants": ["Pack of 6", "Pack of 12", "Pack of 30", "Tray of 6", "Family 24"], "price_range": (45, 380)},
    {"category_slug": "eggs", "slug": "country-eggs", "name": "Country & Quail Eggs", "description": "Country eggs, quail eggs",
     "noun": "Country Eggs", "variants": ["Pack of 6", "Pack of 12", "Quail 24 pcs", "Tray of 30", "Mini Pack"], "price_range": (80, 480)},
    {"category_slug": "eggs", "slug": "egg-specials", "name": "Egg Specials", "description": "Boiled, omelette mix, egg whites",
     "noun": "Boiled Eggs Ready", "variants": ["Pack of 4", "Pack of 6", "Pack of 12", "Egg Whites 200g", "Liquid Egg 250ml"], "price_range": (60, 380)},
    # --- processed-meats ---
    {"category_slug": "processed-meats", "slug": "sausages-salami", "name": "Sausages & Salami", "description": "Chicken sausages, pepperoni, salami",
     "noun": "Chicken Sausages", "variants": ["250g", "500g", "1kg", "Family Pack", "Mini Pack"], "price_range": (180, 980)},
    {"category_slug": "processed-meats", "slug": "bacon-ham", "name": "Bacon & Ham", "description": "Bacon strips, ham slices, smoked",
     "noun": "Chicken Bacon", "variants": ["200g", "400g", "Pack of 2", "Smoked Ham 200g", "Family Pack"], "price_range": (240, 1280)},
    {"category_slug": "processed-meats", "slug": "cold-cuts", "name": "Cold Cuts & Spreads", "description": "Mortadella, pate, smoked turkey",
     "noun": "Smoked Turkey Slices", "variants": ["100g", "200g", "400g", "Family Pack", "Mini Pack"], "price_range": (220, 1180)},
    # --- marinated-cuts ---
    {"category_slug": "marinated-cuts", "slug": "kebab-tikka-ready", "name": "Kebabs & Tikkas", "description": "Sheekh, malai, hariyali, tandoori",
     "noun": "Chicken Malai Tikka", "variants": ["250g", "500g", "1kg", "Family Pack", "Combo Kit"], "price_range": (220, 1480)},
    {"category_slug": "marinated-cuts", "slug": "biryani-kits", "name": "Biryani Kits", "description": "Chicken, mutton biryani kits",
     "noun": "Chicken Biryani Kit", "variants": ["Serves 2", "Serves 4", "Family", "Hyderabadi", "Lucknowi Pack"], "price_range": (380, 1480)},
    {"category_slug": "marinated-cuts", "slug": "marinated-fish", "name": "Marinated Fish", "description": "Tandoori fish, fry-ready prawns",
     "noun": "Tandoori Fish Marinated", "variants": ["250g", "500g", "1kg", "Prawns 500g", "Family Pack"], "price_range": (280, 1680)},
    # --- exotic-meats ---
    {"category_slug": "exotic-meats", "slug": "lamb-cuts", "name": "Lamb", "description": "Lamb chops, leg, mince, racks",
     "noun": "Lamb Chops", "variants": ["500g", "1kg", "Mince 500g", "Leg 1.5kg", "Rack 500g"], "price_range": (680, 2980)},
    {"category_slug": "exotic-meats", "slug": "turkey-duck", "name": "Turkey & Duck", "description": "Whole turkey, duck, smoked",
     "noun": "Smoked Turkey", "variants": ["500g", "1kg", "Whole Bird", "Duck 1kg", "Sliced 200g"], "price_range": (480, 4980)},
    {"category_slug": "exotic-meats", "slug": "exotic-seafood", "name": "Exotic Seafood", "description": "Salmon, tuna, scallops, octopus",
     "noun": "Norwegian Salmon", "variants": ["250g", "500g", "1kg", "Steaks 500g", "Fillet 750g"], "price_range": (580, 3980)},
    # --- makeup ---
    {"category_slug": "makeup", "slug": "lipsticks", "name": "Lipsticks & Glosses", "description": "Matte, satin, liquid, glosses",
     "noun": "Matte Lipstick", "variants": ["Single", "Trio Pack", "Liquid 6ml", "Mini Trial", "Gift Set"], "price_range": (199, 2980)},
    {"category_slug": "makeup", "slug": "foundation-concealer", "name": "Foundation & Concealer", "description": "Liquid, powder, BB, CC, concealers",
     "noun": "Liquid Foundation", "variants": ["30ml", "50ml", "Concealer 10ml", "Mini Trial", "Combo"], "price_range": (250, 4980)},
    {"category_slug": "makeup", "slug": "eyes-cheeks", "name": "Eyes & Cheeks", "description": "Eyeliner, kajal, mascara, blush",
     "noun": "Liquid Eyeliner", "variants": ["2ml", "3ml", "Mascara 10ml", "Blush 5g", "Combo"], "price_range": (149, 2980)},
    # --- fragrances ---
    {"category_slug": "fragrances", "slug": "womens-perfumes", "name": "Women's Perfumes", "description": "EDP, EDT, designer scents",
     "noun": "Women's Eau de Parfum", "variants": ["30ml", "50ml", "100ml EDT", "75ml EDP", "Travel 10ml"], "price_range": (399, 7980)},
    {"category_slug": "fragrances", "slug": "mens-perfumes", "name": "Men's Perfumes", "description": "Cologne, EDT, fresh scents",
     "noun": "Men's Eau de Toilette", "variants": ["50ml", "100ml", "Travel 30ml", "Gift Box", "Twin Pack"], "price_range": (399, 6980)},
    {"category_slug": "fragrances", "slug": "body-mists", "name": "Body Mists", "description": "Light fragrances, body sprays",
     "noun": "Body Mist", "variants": ["100ml", "150ml", "250ml", "Travel 50ml", "Combo"], "price_range": (199, 1480)},
    # --- premium-skincare ---
    {"category_slug": "premium-skincare", "slug": "serums", "name": "Serums", "description": "Vitamin C, niacinamide, retinol",
     "noun": "Vitamin C Serum", "variants": ["10ml", "30ml", "Combo", "50ml", "Travel 5ml"], "price_range": (299, 2480)},
    {"category_slug": "premium-skincare", "slug": "moisturisers-premium", "name": "Moisturisers", "description": "Day cream, night cream, hydrators",
     "noun": "Day Cream", "variants": ["30g", "50g", "Night 50g", "Combo", "Mini 10g"], "price_range": (250, 2980)},
    {"category_slug": "premium-skincare", "slug": "sunscreens", "name": "Sunscreens", "description": "SPF 30, 50, mineral, gel",
     "noun": "SPF 50 Sunscreen", "variants": ["50ml", "100ml", "Tube 75ml", "Combo", "Travel 30ml"], "price_range": (199, 1480)},
    # --- mens-skincare ---
    {"category_slug": "mens-skincare", "slug": "mens-face-wash", "name": "Men's Face Wash", "description": "Charcoal, cooling, anti-acne",
     "noun": "Men's Charcoal Face Wash", "variants": ["50ml", "100ml", "150ml", "Pump 200ml", "Combo Twin"], "price_range": (120, 580)},
    {"category_slug": "mens-skincare", "slug": "mens-moisturiser", "name": "Men's Moisturiser", "description": "Oil-free, gel-based, anti-fatigue",
     "noun": "Men's Moisturiser", "variants": ["50g", "75g", "100g", "Combo", "Mini Trial"], "price_range": (180, 780)},
    {"category_slug": "mens-skincare", "slug": "mens-beard-skincare", "name": "Beard Skincare", "description": "Beard wash, oil, balms",
     "noun": "Beard Wash", "variants": ["100ml", "150ml", "Combo Oil+Wash", "200ml", "Mini Kit"], "price_range": (160, 980)},
    # --- hair-styling ---
    {"category_slug": "hair-styling", "slug": "hair-serums-styling", "name": "Hair Serums", "description": "Frizz-control, shine, heat protection",
     "noun": "Hair Serum", "variants": ["50ml", "100ml", "200ml", "Combo", "Mini 30ml"], "price_range": (250, 1280)},
    {"category_slug": "hair-styling", "slug": "hair-colour", "name": "Hair Colour & Dye", "description": "Permanent, semi-permanent, henna",
     "noun": "Hair Colour Cream", "variants": ["20ml + 60ml Sachet", "Box Kit", "150ml", "Combo", "Refill"], "price_range": (120, 980)},
    {"category_slug": "hair-styling", "slug": "styling-tools", "name": "Styling Tools", "description": "Dryers, straighteners, curlers",
     "noun": "Hair Dryer", "variants": ["1200W", "1600W", "2000W Pro", "Travel", "Combo with Brush"], "price_range": (799, 8980)},
    # --- nail-care ---
    {"category_slug": "nail-care", "slug": "nail-polish", "name": "Nail Polish", "description": "Glossy, matte, gel finish",
     "noun": "Nail Polish", "variants": ["Single 8ml", "Set of 3", "Set of 6", "Mini 4ml", "Gift Pack"], "price_range": (99, 980)},
    {"category_slug": "nail-care", "slug": "nail-care-treat", "name": "Nail Treatment", "description": "Strengtheners, removers, cuticle oil",
     "noun": "Nail Strengthener", "variants": ["10ml", "15ml", "Remover 100ml", "Combo", "Travel 5ml"], "price_range": (89, 580)},
    {"category_slug": "nail-care", "slug": "nail-art-kits", "name": "Nail Art & Kits", "description": "Nail art, decals, manicure kits",
     "noun": "Nail Art Kit", "variants": ["Mini Kit", "Standard Kit", "Pro Kit", "Decals Pack", "Combo"], "price_range": (199, 1680)},
    # --- bath-body ---
    {"category_slug": "bath-body", "slug": "shower-gels", "name": "Shower Gels & Body Wash", "description": "Moisturising, fruity, fresh",
     "noun": "Shower Gel", "variants": ["250ml", "500ml", "750ml", "Travel 100ml", "Combo"], "price_range": (140, 980)},
    {"category_slug": "bath-body", "slug": "body-lotions", "name": "Body Lotions", "description": "Moisturising, brightening, sun-care",
     "noun": "Body Lotion", "variants": ["100ml", "250ml", "400ml", "Pump 600ml", "Mini Travel 50ml"], "price_range": (140, 980)},
    {"category_slug": "bath-body", "slug": "body-scrubs", "name": "Body Scrubs & Bath", "description": "Coffee, salt, sugar scrubs, bath salts",
     "noun": "Coffee Body Scrub", "variants": ["100g", "200g", "Combo", "300g", "Travel 50g"], "price_range": (199, 1280)},
    # --- ethnic-bridal ---
    {"category_slug": "ethnic-bridal", "slug": "henna-mehendi", "name": "Henna & Mehendi", "description": "Henna cones, powder, kits",
     "noun": "Mehendi Cone Pack", "variants": ["Pack of 4", "Pack of 12", "Powder 100g", "Bridal Kit", "Pre-mixed 20g"], "price_range": (49, 580)},
    {"category_slug": "ethnic-bridal", "slug": "bridal-kits", "name": "Bridal Kits", "description": "Bridal makeup, sindoor, bindis",
     "noun": "Bridal Makeup Kit", "variants": ["Mini Kit", "Standard", "Premium", "Custom", "Pro Kit"], "price_range": (799, 7980)},
    {"category_slug": "ethnic-bridal", "slug": "traditional-ubtans", "name": "Ubtans & Traditional", "description": "Ubtan powders, kumkumadi, multani",
     "noun": "Ubtan Powder", "variants": ["100g", "200g", "500g", "Combo", "Mini 50g"], "price_range": (149, 880)},
    # --- mom-baby-beauty ---
    {"category_slug": "mom-baby-beauty", "slug": "stretch-mark", "name": "Stretch Mark & Belly", "description": "Stretch mark oils, creams",
     "noun": "Stretch Mark Cream", "variants": ["100ml", "200ml", "Combo Oil+Cream", "Pump 250ml", "Trial 50ml"], "price_range": (380, 1480)},
    {"category_slug": "mom-baby-beauty", "slug": "baby-massage-oils", "name": "Baby Massage", "description": "Baby massage oil, balms",
     "noun": "Baby Massage Oil", "variants": ["100ml", "200ml", "500ml", "Combo", "Pump 250ml"], "price_range": (140, 680)},
    {"category_slug": "mom-baby-beauty", "slug": "pregnancy-essentials", "name": "Pregnancy Essentials", "description": "Belly butter, nipple cream",
     "noun": "Belly Butter", "variants": ["100g", "200g", "Combo", "Pump 250g", "Travel 50g"], "price_range": (380, 1280)},
    # --- dermatologist ---
    {"category_slug": "dermatologist", "slug": "acne-treatment", "name": "Acne Treatment", "description": "Salicylic acid, BHA, spot treatments",
     "noun": "Acne Spot Treatment", "variants": ["10ml", "30ml", "Combo Cleanser", "Pump 50ml", "Travel 5ml"], "price_range": (280, 1980)},
    {"category_slug": "dermatologist", "slug": "anti-ageing", "name": "Anti-Ageing", "description": "Retinol, peptides, anti-wrinkle",
     "noun": "Retinol Serum", "variants": ["15ml", "30ml", "Combo", "Pump 50ml", "Mini 5ml"], "price_range": (480, 4980)},
    {"category_slug": "dermatologist", "slug": "brightening-treatment", "name": "Brightening", "description": "Hyperpigmentation, vitamin C peels",
     "noun": "Brightening Serum", "variants": ["15ml", "30ml", "Combo Sunscreen", "Pump 50ml", "Mini 5ml"], "price_range": (380, 2980)},
    # --- notebooks ---
    {"category_slug": "notebooks", "slug": "spiral-notebooks", "name": "Spiral Notebooks", "description": "A4, A5 spiral, ruled, unruled",
     "noun": "Spiral Notebook A4 Ruled", "variants": ["100 Pages", "200 Pages", "Pack of 6", "Pack of 12", "A5 200 Pages"], "price_range": (40, 580)},
    {"category_slug": "notebooks", "slug": "long-notebooks", "name": "Long Notebooks", "description": "Long ruled, register, fool's cap",
     "noun": "Long Notebook Ruled", "variants": ["120 Pages", "200 Pages", "Pack of 6", "Register 400 Pages", "Pack of 12"], "price_range": (40, 680)},
    {"category_slug": "notebooks", "slug": "journals-diaries", "name": "Journals & Diaries", "description": "Hardbound, dotted, daily diaries",
     "noun": "Hardbound Journal A5", "variants": ["192 Pages", "288 Pages", "Dotted A5", "Daily Diary 2026", "Combo Pack"], "price_range": (199, 1980)},
    # --- pens-pencils ---
    {"category_slug": "pens-pencils", "slug": "ballpoint-pens", "name": "Ballpoint Pens", "description": "Blue, black, retractable pens",
     "noun": "Ballpoint Pen", "variants": ["Pack of 10", "Pack of 5", "Single", "Pack of 25", "Refill Pack"], "price_range": (20, 380)},
    {"category_slug": "pens-pencils", "slug": "gel-pens", "name": "Gel Pens", "description": "Gel ink, fast-flow, fine tip",
     "noun": "Gel Pen", "variants": ["Pack of 10", "Pack of 5", "Single", "Pack of 25", "Refill Pack"], "price_range": (30, 480)},
    {"category_slug": "pens-pencils", "slug": "pencils-sharpeners", "name": "Pencils & Sharpeners", "description": "HB, 2B, mechanical, kits",
     "noun": "Pencils HB", "variants": ["Pack of 10", "Pack of 20", "Mechanical 0.5mm", "Kit with Sharpener", "Box of 12"], "price_range": (20, 480)},
    # --- school-bags ---
    {"category_slug": "school-bags", "slug": "backpacks-school", "name": "School Backpacks", "description": "Class 1-5, 6-10, college bags",
     "noun": "School Backpack", "variants": ["Junior 28L", "Middle School 32L", "Senior 38L", "Trolley", "Premium"], "price_range": (499, 3980)},
    {"category_slug": "school-bags", "slug": "lunch-bags", "name": "Lunch Bags & Boxes", "description": "Insulated lunch bags, tiffin boxes",
     "noun": "Insulated Lunch Bag", "variants": ["Standard", "Large", "Kids 3-pc Set", "Family", "Travel"], "price_range": (199, 1480)},
    {"category_slug": "school-bags", "slug": "water-bottles", "name": "Water Bottles", "description": "Stainless steel, sipper, glass",
     "noun": "Steel Water Bottle", "variants": ["500ml", "750ml", "1L", "Kids 350ml", "Sipper 600ml"], "price_range": (199, 1980)},
    # --- art-supplies ---
    {"category_slug": "art-supplies", "slug": "colours-paints", "name": "Colours & Paints", "description": "Crayons, watercolors, acrylics",
     "noun": "Wax Crayons", "variants": ["Pack of 12", "Pack of 24", "Pack of 50", "Jumbo Pack", "Set of 100"], "price_range": (40, 980)},
    {"category_slug": "art-supplies", "slug": "sketch-pens", "name": "Sketch Pens & Markers", "description": "Sketch pens, markers, highlighters",
     "noun": "Sketch Pens", "variants": ["Pack of 12", "Pack of 24", "Pack of 60", "Pack of 36", "Combo Set"], "price_range": (60, 980)},
    {"category_slug": "art-supplies", "slug": "canvas-easel", "name": "Canvas, Easel & Brushes", "description": "Canvas, brushes, easels, drawing kits",
     "noun": "Stretched Canvas", "variants": ["Pack of 3", "Pack of 5", "Mini 8-inch", "Large 16x20", "Combo Brush Kit"], "price_range": (199, 2980)},
    # --- office-supplies ---
    {"category_slug": "office-supplies", "slug": "files-folders", "name": "Files & Folders", "description": "Box files, ring binders, expanding files",
     "noun": "Box File", "variants": ["Pack of 6", "Pack of 12", "Single", "Premium Folder", "Pack of 24"], "price_range": (60, 980)},
    {"category_slug": "office-supplies", "slug": "staplers-punches", "name": "Staplers & Punches", "description": "Staplers, punches, paper clips",
     "noun": "Heavy Duty Stapler", "variants": ["Single", "With Pins", "Mini", "Pro 100-sheet", "Combo Punch"], "price_range": (149, 1480)},
    {"category_slug": "office-supplies", "slug": "tapes-glues", "name": "Tapes, Glues & Adhesives", "description": "Cello tape, glue sticks, super glue",
     "noun": "Cello Tape", "variants": ["Pack of 6", "Pack of 12", "Wide", "Mini 5-pack", "Premium 1-inch"], "price_range": (60, 480)},
    # --- fiction-books ---
    {"category_slug": "fiction-books", "slug": "indian-fiction", "name": "Indian Fiction", "description": "Contemporary, classic Indian authors",
     "noun": "Indian Fiction Novel", "variants": ["Paperback", "Hardcover", "Box Set", "Limited Edition", "Combo of 3"], "price_range": (199, 2480)},
    {"category_slug": "fiction-books", "slug": "international-fiction", "name": "International Fiction", "description": "Bestsellers, contemporary fiction",
     "noun": "International Fiction Novel", "variants": ["Paperback", "Hardcover", "Box Set", "Special Edition", "Combo of 3"], "price_range": (299, 2980)},
    {"category_slug": "fiction-books", "slug": "fantasy-thrillers", "name": "Fantasy & Thrillers", "description": "Fantasy, sci-fi, thrillers, mystery",
     "noun": "Fantasy Novel", "variants": ["Paperback", "Hardcover", "Trilogy Box", "Limited Edition", "Series Pack"], "price_range": (299, 3480)},
    # --- non-fiction ---
    {"category_slug": "non-fiction", "slug": "self-help", "name": "Self-Help", "description": "Productivity, mindfulness, finance",
     "noun": "Self-Help Bestseller", "variants": ["Paperback", "Hardcover", "Workbook Combo", "Special Edition", "Pack of 3"], "price_range": (199, 1980)},
    {"category_slug": "non-fiction", "slug": "biographies", "name": "Biographies & Memoir", "description": "Leaders, sportspeople, celebrities",
     "noun": "Biography", "variants": ["Paperback", "Hardcover", "Illustrated", "Limited Edition", "Combo of 2"], "price_range": (299, 2480)},
    {"category_slug": "non-fiction", "slug": "business-finance", "name": "Business & Finance", "description": "Strategy, investing, leadership",
     "noun": "Business Book", "variants": ["Paperback", "Hardcover", "Workbook Combo", "Special Edition", "Set of 2"], "price_range": (299, 2980)},
    # --- textbooks-academic ---
    {"category_slug": "textbooks-academic", "slug": "ncert-school", "name": "NCERT & School Texts", "description": "NCERT, state board textbooks",
     "noun": "NCERT Textbook", "variants": ["Class 6", "Class 8", "Class 10 Pack", "Class 12 Pack", "Combo Set"], "price_range": (99, 1480)},
    {"category_slug": "textbooks-academic", "slug": "jee-neet-prep", "name": "JEE & NEET Prep", "description": "JEE Main, Advanced, NEET books",
     "noun": "JEE Advanced Practice Book", "variants": ["Physics", "Chemistry", "Maths", "Set of 3", "Combo + Solutions"], "price_range": (399, 4980)},
    {"category_slug": "textbooks-academic", "slug": "engineering-medical-reference", "name": "Engineering & Medical Reference", "description": "GATE, NEET PG, AIIMS reference",
     "noun": "Reference Textbook", "variants": ["Single Volume", "Volume 1+2", "Set of 3", "Special Edition", "Combo + Solutions"], "price_range": (499, 5980)},
    # --- kids-learning ---
    {"category_slug": "kids-learning", "slug": "activity-books", "name": "Activity & Workbooks", "description": "Coloring, sticker, puzzle books",
     "noun": "Kids Activity Book", "variants": ["Single", "Pack of 3", "Pack of 6", "Combo Sticker", "Box Set"], "price_range": (99, 1480)},
    {"category_slug": "kids-learning", "slug": "picture-storybooks", "name": "Picture & Storybooks", "description": "Bedtime, fairy tales, illustrated",
     "noun": "Children's Storybook", "variants": ["Single", "Pack of 3", "Pack of 6", "Hardcover", "Box Set of 10"], "price_range": (149, 1980)},
    {"category_slug": "kids-learning", "slug": "comics-graphic", "name": "Comics & Graphic Novels", "description": "Tinkle, Amar Chitra, Marvel, DC",
     "noun": "Children's Comic", "variants": ["Single Issue", "Pack of 3", "Pack of 6", "Box Set", "Special Edition"], "price_range": (99, 1480)},
    # --- exam-prep ---
    {"category_slug": "exam-prep", "slug": "upsc-prep", "name": "UPSC & Civil Services", "description": "Prelims, mains, optional subjects",
     "noun": "UPSC Prelims Book", "variants": ["Single Subject", "Combo of 3", "Full Pack", "Test Series Combo", "Solved Papers"], "price_range": (499, 5980)},
    {"category_slug": "exam-prep", "slug": "banking-ssc", "name": "Banking & SSC", "description": "Banking, SSC, RRB, state govt exams",
     "noun": "Banking Prep Book", "variants": ["Single Subject", "Combo of 3", "Full Pack", "Solved Papers", "Test Series Combo"], "price_range": (299, 2980)},
    {"category_slug": "exam-prep", "slug": "english-aptitude", "name": "English & Aptitude", "description": "Vocab, grammar, quant, reasoning",
     "noun": "Aptitude Book", "variants": ["Single Topic", "Combo of 3", "Full Pack", "Practice Workbook", "Test Series Combo"], "price_range": (199, 1480)},
    # --- dog-food ---
    {"category_slug": "dog-food", "slug": "dog-dry-food", "name": "Dog Dry Food", "description": "Adult, puppy, senior, breed-specific",
     "noun": "Adult Dog Dry Food", "variants": ["1kg", "3kg", "10kg", "Puppy 1kg", "Senior 3kg"], "price_range": (299, 4980)},
    {"category_slug": "dog-food", "slug": "dog-wet-food", "name": "Dog Wet Food", "description": "Gravy, pate, chunks, broth",
     "noun": "Dog Wet Food Gravy", "variants": ["Pack of 4 x 85g", "Pack of 12", "Single 400g", "Family Pack", "Mini Pack"], "price_range": (199, 1980)},
    {"category_slug": "dog-food", "slug": "dog-treats", "name": "Dog Treats", "description": "Biscuits, dental sticks, jerky",
     "noun": "Dog Training Treats", "variants": ["100g", "250g", "500g", "Combo Pack", "Mini Pack"], "price_range": (140, 1280)},
    # --- cat-food ---
    {"category_slug": "cat-food", "slug": "cat-dry-food", "name": "Cat Dry Food", "description": "Adult, kitten, hairball, indoor",
     "noun": "Adult Cat Dry Food", "variants": ["1kg", "3kg", "7kg", "Kitten 1kg", "Hairball 1.5kg"], "price_range": (299, 4980)},
    {"category_slug": "cat-food", "slug": "cat-wet-food", "name": "Cat Wet Food", "description": "Pouches, cans, gravy, jelly",
     "noun": "Cat Wet Food Pouch", "variants": ["Pack of 4 x 85g", "Pack of 12", "Single 100g", "Variety Pack", "Family Pack"], "price_range": (199, 1980)},
    {"category_slug": "cat-food", "slug": "cat-treats", "name": "Cat Treats & Supplements", "description": "Sticks, biscuits, vitamins",
     "noun": "Cat Treats", "variants": ["50g", "150g", "Combo", "Vitamin Sticks", "Mini Pack"], "price_range": (140, 980)},
    # --- fish-aquarium ---
    {"category_slug": "fish-aquarium", "slug": "fish-food", "name": "Fish Food", "description": "Flakes, pellets, granules",
     "noun": "Fish Food Flakes", "variants": ["50g", "100g", "200g", "500g Tub", "Combo"], "price_range": (99, 980)},
    {"category_slug": "fish-aquarium", "slug": "aquarium-filters", "name": "Filters & Pumps", "description": "Air pumps, internal filters",
     "noun": "Aquarium Air Pump", "variants": ["Single Outlet", "Twin Outlet", "Mini", "Pro 4-Outlet", "Submersible Filter"], "price_range": (299, 3980)},
    {"category_slug": "fish-aquarium", "slug": "aquarium-decor", "name": "Aquarium Decor", "description": "Plants, gravel, lights, backdrop",
     "noun": "Aquarium Decor Plant", "variants": ["Single", "Pack of 3", "Pack of 6", "Mini Decor Set", "Combo"], "price_range": (149, 1480)},
    # --- bird-supplies ---
    {"category_slug": "bird-supplies", "slug": "bird-food", "name": "Bird Food", "description": "Seed mixes, pellets, fruit treats",
     "noun": "Bird Seed Mix", "variants": ["500g", "1kg", "2kg", "Premium 500g", "Combo"], "price_range": (199, 1480)},
    {"category_slug": "bird-supplies", "slug": "bird-cages", "name": "Bird Cages", "description": "Wire cages, breeding cages",
     "noun": "Bird Wire Cage", "variants": ["Small", "Medium", "Large", "Travel Cage", "Premium Aviary"], "price_range": (599, 5980)},
    {"category_slug": "bird-supplies", "slug": "bird-toys-perches", "name": "Bird Toys & Perches", "description": "Swings, mirrors, perches, bells",
     "noun": "Bird Swing Toy", "variants": ["Single", "Pack of 3", "Pack of 5", "Bell Toy", "Combo"], "price_range": (199, 1480)},
    # --- pet-grooming ---
    {"category_slug": "pet-grooming", "slug": "pet-shampoo", "name": "Pet Shampoo", "description": "Dog, cat, anti-tick shampoos",
     "noun": "Pet Shampoo", "variants": ["200ml", "500ml", "1L", "Combo Conditioner", "Mini 100ml"], "price_range": (199, 1480)},
    {"category_slug": "pet-grooming", "slug": "pet-brushes", "name": "Brushes & Clippers", "description": "Slicker brushes, de-shedders, clippers",
     "noun": "Pet Slicker Brush", "variants": ["Small", "Medium", "Large", "De-shedder", "Pro Clipper"], "price_range": (199, 3980)},
    {"category_slug": "pet-grooming", "slug": "pet-paw-care", "name": "Paw & Dental", "description": "Paw balms, dental sticks, ear cleaners",
     "noun": "Pet Paw Balm", "variants": ["50g", "100g", "Combo", "Pump 150g", "Mini 30g"], "price_range": (199, 980)},
    # --- pet-toys ---
    {"category_slug": "pet-toys", "slug": "chew-toys", "name": "Chew Toys", "description": "Rubber, rope, dental chews",
     "noun": "Rubber Chew Toy", "variants": ["Small", "Medium", "Large", "Pack of 3", "Combo Set"], "price_range": (199, 1980)},
    {"category_slug": "pet-toys", "slug": "fetch-toys", "name": "Fetch Toys", "description": "Balls, frisbees, tug ropes",
     "noun": "Tennis Fetch Ball", "variants": ["Pack of 3", "Pack of 6", "Single", "Frisbee", "Combo Set"], "price_range": (149, 1280)},
    {"category_slug": "pet-toys", "slug": "interactive-toys", "name": "Interactive & Puzzle", "description": "Puzzle feeders, snuffle mats",
     "noun": "Puzzle Feeder", "variants": ["Beginner", "Intermediate", "Advanced", "Snuffle Mat", "Combo"], "price_range": (399, 3980)},
    # --- pet-medicines ---
    {"category_slug": "pet-medicines", "slug": "deworm-tick", "name": "Deworm & Tick Care", "description": "Tablets, drops, sprays",
     "noun": "Pet Dewormer Tablet", "variants": ["Pack of 4", "Pack of 8", "Drops 30ml", "Spray 100ml", "Combo Kit"], "price_range": (199, 1480)},
    {"category_slug": "pet-medicines", "slug": "pet-supplements", "name": "Vitamins & Supplements", "description": "Multivitamins, calcium, joint care",
     "noun": "Pet Multivitamin", "variants": ["100g", "250g", "Pack of 60 Tablets", "Combo", "Mini Pack"], "price_range": (299, 1980)},
    {"category_slug": "pet-medicines", "slug": "first-aid-pet", "name": "Pet First Aid", "description": "Wound spray, antiseptic, eye drops",
     "noun": "Pet Wound Antiseptic Spray", "variants": ["50ml", "100ml", "200ml", "Combo Kit", "Travel Pack"], "price_range": (199, 980)},
    # --- pet-accessories ---
    {"category_slug": "pet-accessories", "slug": "collars-leashes", "name": "Collars & Leashes", "description": "Collars, leashes, harness",
     "noun": "Pet Collar Adjustable", "variants": ["Small", "Medium", "Large", "Combo Leash", "Reflective"], "price_range": (199, 1980)},
    {"category_slug": "pet-accessories", "slug": "bowls-feeders", "name": "Bowls & Feeders", "description": "Steel bowls, slow feeders, water",
     "noun": "Pet Steel Bowl", "variants": ["Small", "Medium", "Large", "Twin Set", "Slow Feeder"], "price_range": (199, 1480)},
    {"category_slug": "pet-accessories", "slug": "pet-beds", "name": "Beds & Mats", "description": "Cushioned beds, mats, blankets",
     "noun": "Pet Cushioned Bed", "variants": ["Small", "Medium", "Large", "XL", "Premium Sofa Style"], "price_range": (499, 4980)},
    # --- cookware ---
    {"category_slug": "cookware", "slug": "pressure-cookers", "name": "Pressure Cookers", "description": "Outer lid, inner lid, induction",
     "noun": "Pressure Cooker", "variants": ["3L", "5L", "7.5L", "Induction 5L", "Combo 3+5L"], "price_range": (899, 4980)},
    {"category_slug": "cookware", "slug": "pans-kadhais", "name": "Pans & Kadhais", "description": "Tawa, kadhai, frying pans, woks",
     "noun": "Non-Stick Kadhai", "variants": ["22cm", "24cm", "28cm", "Combo Lid", "30cm Family"], "price_range": (599, 3980)},
    {"category_slug": "cookware", "slug": "cookware-sets", "name": "Cookware Sets", "description": "Induction sets, granite, ceramic",
     "noun": "Cookware Set", "variants": ["3-pc Set", "5-pc Set", "7-pc Set", "10-pc Pro", "Induction 5-pc"], "price_range": (1980, 14980)},
    # --- dinnerware ---
    {"category_slug": "dinnerware", "slug": "dinner-sets", "name": "Dinner Sets", "description": "Opalware, ceramic, melamine sets",
     "noun": "Opal Dinner Set", "variants": ["18-pc", "27-pc", "33-pc", "Family 47-pc", "Premium 50-pc"], "price_range": (1480, 12980)},
    {"category_slug": "dinnerware", "slug": "plates-bowls", "name": "Plates & Bowls", "description": "Quarter plates, soup bowls, dessert",
     "noun": "Quarter Plate Set", "variants": ["Set of 6", "Set of 12", "Soup Bowls 6", "Dessert Set 6", "Family Set"], "price_range": (380, 2980)},
    {"category_slug": "dinnerware", "slug": "glassware", "name": "Glassware", "description": "Tumblers, juice, wine glasses",
     "noun": "Tumbler Set", "variants": ["Set of 6", "Set of 12", "Wine Set", "Juice Set", "Beer Mugs Set"], "price_range": (280, 2480)},
    # --- storage-containers ---
    {"category_slug": "storage-containers", "slug": "kitchen-jars", "name": "Kitchen Jars", "description": "Air-tight, modular, glass jars",
     "noun": "Airtight Jar Set", "variants": ["Set of 6", "Set of 12", "Set of 18", "Combo 24", "Glass Set 6"], "price_range": (480, 2980)},
    {"category_slug": "storage-containers", "slug": "lunch-boxes", "name": "Lunch Boxes", "description": "Steel, plastic, insulated tiffin",
     "noun": "Steel Lunch Box", "variants": ["3-Container", "4-Container", "Insulated", "Kids 2-pc", "Family Set"], "price_range": (380, 2480)},
    {"category_slug": "storage-containers", "slug": "modular-storage", "name": "Modular Storage", "description": "Stackable, drawer organisers, racks",
     "noun": "Modular Stackable Container", "variants": ["Set of 4", "Set of 8", "Set of 12", "Drawer Combo", "Rack Combo"], "price_range": (399, 2980)},
    # --- small-appliances ---
    {"category_slug": "small-appliances", "slug": "irons-steamers", "name": "Irons & Steamers", "description": "Dry, steam, garment steamers",
     "noun": "Steam Iron", "variants": ["1200W", "1600W", "2000W Pro", "Travel", "Garment Steamer"], "price_range": (899, 4980)},
    {"category_slug": "small-appliances", "slug": "fans-coolers", "name": "Fans & Coolers", "description": "Table, tower, pedestal fans",
     "noun": "Tower Fan", "variants": ["Small", "Medium", "Large", "Pedestal Combo", "Table Fan"], "price_range": (1980, 9980)},
    {"category_slug": "small-appliances", "slug": "vacuum-cleaners", "name": "Vacuum Cleaners", "description": "Handheld, robotic, wet-dry",
     "noun": "Vacuum Cleaner", "variants": ["Handheld", "Upright", "Robotic", "Wet+Dry", "Pro 2000W"], "price_range": (1480, 39980)},
    # --- cleaning ---
    {"category_slug": "cleaning", "slug": "laundry-detergent", "name": "Laundry Detergent", "description": "Powder, liquid, capsules",
     "noun": "Laundry Detergent Powder", "variants": ["1kg", "2kg", "4kg", "Liquid 1L", "Capsules Pack"], "price_range": (180, 980)},
    {"category_slug": "cleaning", "slug": "floor-cleaners", "name": "Floor & Surface Cleaners", "description": "Lizol, Mr Muscle, Domex",
     "noun": "Floor Cleaner", "variants": ["500ml", "1L", "2L", "5L Family", "Combo"], "price_range": (99, 580)},
    {"category_slug": "cleaning", "slug": "dishwash", "name": "Dishwash & Utensil", "description": "Liquid, bar, scrub pads",
     "noun": "Dishwash Liquid", "variants": ["250ml", "500ml", "1L", "Family Pouch 1.5L", "Combo Scrub"], "price_range": (60, 380)},
    # --- home-decor ---
    {"category_slug": "home-decor", "slug": "wall-art", "name": "Wall Art & Frames", "description": "Posters, paintings, photo frames",
     "noun": "Wall Art Frame", "variants": ["Single A4", "Set of 3", "Set of 5", "Large Canvas", "Collage Set"], "price_range": (299, 4980)},
    {"category_slug": "home-decor", "slug": "candles-fragrance", "name": "Candles & Fragrance", "description": "Scented candles, diffusers, incense",
     "noun": "Scented Candle", "variants": ["Single", "Set of 3", "Diffuser Combo", "Gift Box", "Aroma Oil Set"], "price_range": (199, 2480)},
    {"category_slug": "home-decor", "slug": "vases-showpieces", "name": "Vases & Showpieces", "description": "Vases, figurines, decor accents",
     "noun": "Ceramic Vase", "variants": ["Single", "Set of 2", "Set of 3", "Large Decor", "Combo Set"], "price_range": (299, 3980)},
    # --- bedding ---
    {"category_slug": "bedding", "slug": "bedsheets-pillow", "name": "Bedsheets & Pillow Covers", "description": "Single, double, king bedsheets",
     "noun": "Bedsheet Set", "variants": ["Single", "Double", "King", "Queen Set", "Combo Pack"], "price_range": (399, 3980)},
    {"category_slug": "bedding", "slug": "blankets-quilts", "name": "Blankets & Quilts", "description": "Fleece, mink, AC quilts, dohar",
     "noun": "Fleece Blanket", "variants": ["Single", "Double", "King", "AC Quilt", "Mink Combo"], "price_range": (399, 4980)},
    {"category_slug": "bedding", "slug": "pillows-mattress", "name": "Pillows & Mattress Toppers", "description": "Memory foam, fibre pillows",
     "noun": "Memory Foam Pillow", "variants": ["Single", "Pack of 2", "King Size", "Travel", "Combo Set"], "price_range": (399, 4980)},
    # --- bath-essentials ---
    {"category_slug": "bath-essentials", "slug": "towels", "name": "Towels", "description": "Bath, face, hand towels",
     "noun": "Bath Towel", "variants": ["Single", "Set of 2", "Family Set of 4", "Hand Towels Set", "Combo"], "price_range": (299, 2980)},
    {"category_slug": "bath-essentials", "slug": "bathmats-rugs", "name": "Bathmats & Rugs", "description": "Cotton, microfiber, anti-skid",
     "noun": "Anti-Skid Bathmat", "variants": ["Single", "Set of 2", "Set of 3", "Premium", "Combo"], "price_range": (199, 1480)},
    {"category_slug": "bath-essentials", "slug": "shower-curtains", "name": "Shower Curtains & Accessories", "description": "Curtains, hooks, shower caps",
     "noun": "Shower Curtain", "variants": ["Standard", "Premium", "With Hooks", "Combo Set", "Eco Pack"], "price_range": (299, 2480)},
    # --- kitchen-tools ---
    {"category_slug": "kitchen-tools", "slug": "knives", "name": "Knives", "description": "Chef's, paring, bread, kitchen sets",
     "noun": "Kitchen Knife Set", "variants": ["3-pc", "5-pc", "7-pc", "Chef's Single", "Combo Block"], "price_range": (480, 3980)},
    {"category_slug": "kitchen-tools", "slug": "choppers-graters", "name": "Choppers & Graters", "description": "Manual choppers, mandoline, graters",
     "noun": "Manual Chopper", "variants": ["350ml", "650ml", "900ml", "Set with Mandoline", "Grater Set"], "price_range": (299, 1980)},
    {"category_slug": "kitchen-tools", "slug": "ladles-spoons", "name": "Ladles & Spoons", "description": "Cooking spoons, ladles, spatulas",
     "noun": "Kitchen Ladle Set", "variants": ["Set of 3", "Set of 5", "Set of 7", "Wooden Set 5", "Silicone Set"], "price_range": (199, 1480)},
    # --- lighting-fixtures ---
    {"category_slug": "lighting-fixtures", "slug": "led-bulbs", "name": "LED Bulbs", "description": "9W, 12W, 18W LED, decorative",
     "noun": "LED Bulb", "variants": ["9W", "12W", "Pack of 4", "Pack of 10", "18W Family"], "price_range": (99, 980)},
    {"category_slug": "lighting-fixtures", "slug": "table-lamps", "name": "Table & Floor Lamps", "description": "Study, decorative, floor lamps",
     "noun": "Table Lamp", "variants": ["Single", "Pair", "Floor Lamp", "Designer", "Study Combo"], "price_range": (499, 4980)},
    {"category_slug": "lighting-fixtures", "slug": "fairy-string-lights", "name": "Fairy & String Lights", "description": "LED strings, rope, fairy lights",
     "noun": "Fairy LED String Lights", "variants": ["5m", "10m", "20m", "Battery Operated", "Solar 10m"], "price_range": (199, 1480)},
    # --- bouquets ---
    {"category_slug": "bouquets", "slug": "rose-bouquets", "name": "Rose Bouquets", "description": "Red, pink, white, mixed roses",
     "noun": "Red Rose Bouquet", "variants": ["6 Stems", "12 Stems", "24 Stems", "Designer 50", "Mini 4 Stems"], "price_range": (399, 4980)},
    {"category_slug": "bouquets", "slug": "mixed-flower-bouquets", "name": "Mixed Flower Bouquets", "description": "Mixed roses, lilies, gerberas, carnations",
     "noun": "Mixed Flower Bouquet", "variants": ["Small", "Medium", "Large", "Designer", "Premium"], "price_range": (499, 4980)},
    {"category_slug": "bouquets", "slug": "exotic-flowers", "name": "Exotic Flowers", "description": "Orchids, tulips, lilies bouquets",
     "noun": "Orchid Bouquet", "variants": ["Small", "Medium", "Large", "Designer", "Premium"], "price_range": (699, 5980)},
    # --- indoor-plants ---
    {"category_slug": "indoor-plants", "slug": "succulents", "name": "Succulents", "description": "Echeveria, cactus, jade, aloe",
     "noun": "Succulent Plant", "variants": ["Mini", "Standard", "Pack of 3", "Pack of 5", "Combo Set"], "price_range": (199, 1980)},
    {"category_slug": "indoor-plants", "slug": "leafy-indoor", "name": "Leafy Indoor Plants", "description": "Money plant, snake, peace lily",
     "noun": "Money Plant", "variants": ["Small", "Medium", "Large", "Hanging", "Combo"], "price_range": (299, 2480)},
    {"category_slug": "indoor-plants", "slug": "bonsai-collection", "name": "Bonsai", "description": "Ficus, jade, juniper bonsai",
     "noun": "Bonsai Plant", "variants": ["Small", "Medium", "Large", "Designer", "Premium"], "price_range": (799, 5980)},
    # --- gardening ---
    {"category_slug": "gardening", "slug": "pots-planters", "name": "Pots & Planters", "description": "Ceramic, terracotta, hanging pots",
     "noun": "Ceramic Pot", "variants": ["Small", "Medium", "Large", "Set of 3", "Hanging"], "price_range": (199, 1980)},
    {"category_slug": "gardening", "slug": "seeds-bulbs", "name": "Seeds & Bulbs", "description": "Veg, herb, flower seeds, bulbs",
     "noun": "Vegetable Seeds Pack", "variants": ["10 Varieties", "20 Varieties", "Herbs Pack", "Flower Bulbs", "Combo Kit"], "price_range": (199, 1480)},
    {"category_slug": "gardening", "slug": "fertilizer-soil", "name": "Fertilizer & Soil", "description": "Compost, NPK, soil mixes",
     "noun": "Organic Compost", "variants": ["1kg", "2kg", "5kg", "Combo NPK", "Soil Mix 5kg"], "price_range": (199, 980)},
    # --- occasion-arrangements ---
    {"category_slug": "occasion-arrangements", "slug": "wedding-arrangements", "name": "Wedding Arrangements", "description": "Bridal, mandap, garlands",
     "noun": "Wedding Bouquet", "variants": ["Bride", "Bridesmaid Set", "Garland Pair", "Mandap Decor", "Combo"], "price_range": (1480, 14980)},
    {"category_slug": "occasion-arrangements", "slug": "anniversary-flowers", "name": "Anniversary", "description": "Red rose hearts, designer, premium",
     "noun": "Anniversary Heart Bouquet", "variants": ["50 Roses", "100 Roses", "Heart Shape", "Designer Box", "Combo Cake"], "price_range": (1280, 9980)},
    {"category_slug": "occasion-arrangements", "slug": "sympathy-arrangements", "name": "Sympathy & Condolence", "description": "White flowers, wreaths, lily arrangements",
     "noun": "Sympathy Arrangement", "variants": ["Small", "Medium", "Large Wreath", "Lily Arrangement", "Designer"], "price_range": (1480, 7980)},
    # --- gym-equipment ---
    {"category_slug": "gym-equipment", "slug": "dumbbells-weights", "name": "Dumbbells & Weights", "description": "Hex, vinyl, adjustable, kettlebells",
     "noun": "Hex Dumbbell Pair", "variants": ["2kg", "5kg", "10kg", "Adjustable 20kg", "Combo Set"], "price_range": (399, 9980)},
    {"category_slug": "gym-equipment", "slug": "yoga-mats", "name": "Yoga Mats & Bands", "description": "Yoga mats, resistance bands, blocks",
     "noun": "Yoga Mat", "variants": ["6mm", "8mm", "Premium 10mm", "Combo with Strap", "Kids Mat"], "price_range": (399, 3980)},
    {"category_slug": "gym-equipment", "slug": "cardio-equipment", "name": "Cardio Equipment", "description": "Skipping ropes, jump trainers, exercise cycles",
     "noun": "Skipping Rope", "variants": ["Standard", "Speed", "Weighted", "Digital Counter", "Exercise Cycle"], "price_range": (199, 19980)},
    # --- sports-gear ---
    {"category_slug": "sports-gear", "slug": "cricket-gear", "name": "Cricket Gear", "description": "Bats, balls, pads, helmets",
     "noun": "Cricket Bat", "variants": ["English Willow", "Kashmir Willow", "Tennis Bat", "Junior", "Pro Kit"], "price_range": (599, 14980)},
    {"category_slug": "sports-gear", "slug": "football-basketball", "name": "Football & Basketball", "description": "Footballs, basketballs, jerseys",
     "noun": "Football Size 5", "variants": ["Standard", "Match", "Pro", "Junior Size 4", "Combo Set"], "price_range": (399, 3980)},
    {"category_slug": "sports-gear", "slug": "badminton-rackets", "name": "Badminton & Tennis", "description": "Rackets, shuttles, balls, kits",
     "noun": "Badminton Racket", "variants": ["Standard", "Pro", "Pair", "Junior", "Combo Kit"], "price_range": (599, 8980)},
    # --- fitness-wearables ---
    {"category_slug": "fitness-wearables", "slug": "fitness-bands", "name": "Fitness Bands", "description": "Step trackers, heart-rate bands",
     "noun": "Fitness Band", "variants": ["Standard", "AMOLED", "Pro Cellular", "Bluetooth Calling", "Kids"], "price_range": (1499, 9980)},
    {"category_slug": "fitness-wearables", "slug": "smart-watches-fitness", "name": "Smart Watches", "description": "Fitness watches, GPS, sports modes",
     "noun": "Sports Smartwatch", "variants": ["Standard", "Pro GPS", "Cellular", "Multi-Sport", "Premium"], "price_range": (2999, 49980)},
    {"category_slug": "fitness-wearables", "slug": "heart-rate-monitors", "name": "Heart-rate Monitors", "description": "Chest straps, arm bands, pulse",
     "noun": "Heart Rate Chest Strap", "variants": ["Bluetooth", "ANT+", "Combo", "Pro Athlete", "Mini"], "price_range": (1499, 14980)},
    # --- athletic-wear ---
    {"category_slug": "athletic-wear", "slug": "athletic-tees", "name": "Athletic T-Shirts", "description": "Dry-fit, running, training tees",
     "noun": "Dry-Fit T-Shirt", "variants": ["S", "M", "L", "XL", "Pack of 2"], "price_range": (499, 2980)},
    {"category_slug": "athletic-wear", "slug": "athletic-shorts", "name": "Shorts & Leggings", "description": "Shorts, leggings, joggers",
     "noun": "Training Shorts", "variants": ["S", "M", "L", "XL", "Leggings Combo"], "price_range": (499, 3480)},
    {"category_slug": "athletic-wear", "slug": "athletic-shoes", "name": "Athletic Shoes", "description": "Running, training, sports shoes",
     "noun": "Running Shoes", "variants": ["UK 7", "UK 8", "UK 9", "UK 10", "UK 11"], "price_range": (1499, 12980)},
]


# ---------------------------------------------------------------------------
# EXTRA PRODUCTS (1365 → PRODUCTS total 1500; 5 per extra subcategory)
# ---------------------------------------------------------------------------

_CATEGORY_BY_SLUG = {cat["slug"]: cat for cat in EXTRA_CATEGORIES}


def _slugify(text: str) -> str:
    """Lowercase ASCII slug. Stable for fixed inputs."""
    out = []
    prev_dash = False
    for ch in text.lower():
        if ch.isalnum():
            out.append(ch)
            prev_dash = False
        elif ch in (" ", "-", "_", "/"):
            if not prev_dash:
                out.append("-")
                prev_dash = True
        elif ch == "&":
            if not prev_dash:
                out.append("-and-")
                prev_dash = True
    return "".join(out).strip("-")


def _generate_extra_products() -> list[dict[str, Any]]:
    """Combine each extra subcategory with its category brand pool to emit 5
    products. Deterministic — no RNG. Prices step uniformly across range."""
    products: list[dict[str, Any]] = []
    seen_slugs: set[str] = set()
    for sub in EXTRA_SUBCATEGORIES:
        cat = _CATEGORY_BY_SLUG[sub["category_slug"]]
        brands = cat["brand_pool"][:5]
        variants = sub["variants"]
        low, high = sub["price_range"]
        for i, brand in enumerate(brands):
            variant = variants[i % len(variants)]
            name = f"{brand} {sub['noun']} ({variant})"
            slug_pieces = [_slugify(brand), _slugify(sub["noun"]), _slugify(variant), str(i)]
            slug = "-".join(p for p in slug_pieces if p)[:90]
            # Disambiguate collisions deterministically (brand+noun+variant can repeat across cats).
            unique_slug = slug
            n = 1
            while unique_slug in seen_slugs:
                unique_slug = f"{slug}-{n}"
                n += 1
            seen_slugs.add(unique_slug)
            price = round(low + (high - low) * i / 4) if high > low else low
            products.append({
                "subcategory_slug": sub["slug"],
                "slug": unique_slug,
                "name": name,
                "description": f"{name} — {sub['description'].lower()}",
                "image_url": f"/images/products/{unique_slug}.jpg",
                "base_price": price,
            })
    return products


EXTRA_PRODUCTS: list[dict[str, Any]] = _generate_extra_products()


# ---------------------------------------------------------------------------
# MUMBAI NEIGHBORHOODS — anchors for store/customer-address generation.
# Tight Mumbai municipal bbox so existing test bbox barely changes.
# (name, lat, lng, pincode)
# ---------------------------------------------------------------------------
MUMBAI_NEIGHBORHOODS: list[tuple[str, float, float, str]] = [
    ("Andheri East", 19.1136, 72.8697, "400069"),
    ("Borivali West", 19.2307, 72.8567, "400092"),
    ("Borivali East", 19.2280, 72.8627, "400066"),
    ("Kandivali East", 19.2106, 72.8722, "400101"),
    ("Kandivali West", 19.2095, 72.8526, "400067"),
    ("Malad West", 19.1864, 72.8489, "400064"),
    ("Malad East", 19.1737, 72.8590, "400097"),
    ("Jogeshwari West", 19.1340, 72.8470, "400102"),
    ("Vile Parle West", 19.1015, 72.8430, "400056"),
    ("Vile Parle East", 19.0995, 72.8553, "400057"),
    ("Santacruz West", 19.0808, 72.8344, "400054"),
    ("Santacruz East", 19.0816, 72.8404, "400055"),
    ("Khar West", 19.0697, 72.8350, "400052"),
    ("Mahim", 19.0418, 72.8398, "400016"),
    ("Matunga", 19.0270, 72.8553, "400019"),
    ("Sion", 19.0395, 72.8625, "400022"),
    ("Wadala", 19.0179, 72.8650, "400031"),
    ("Parel", 18.9988, 72.8412, "400012"),
    ("Byculla", 18.9783, 72.8327, "400027"),
    ("Mumbai Central", 18.9696, 72.8205, "400008"),
    ("Marine Lines", 18.9474, 72.8233, "400002"),
    ("Churchgate", 18.9354, 72.8266, "400020"),
    ("Fort", 18.9322, 72.8347, "400001"),
    ("Nariman Point", 18.9258, 72.8235, "400021"),
    ("Cuffe Parade", 18.9067, 72.8081, "400005"),
    ("Tardeo", 18.9694, 72.8089, "400034"),
    ("Grant Road", 18.9622, 72.8121, "400007"),
    ("Charni Road", 18.9542, 72.8160, "400004"),
    ("Walkeshwar", 18.9528, 72.7950, "400006"),
    ("Malabar Hill", 18.9554, 72.7944, "400006"),
    ("Prabhadevi", 19.0150, 72.8262, "400025"),
    ("Sewri", 18.9986, 72.8576, "400015"),
    ("Chembur", 19.0635, 72.8995, "400071"),
    ("Govandi", 19.0532, 72.9116, "400088"),
    ("Vikhroli East", 19.1101, 72.9268, "400083"),
    ("Vikhroli West", 19.1075, 72.9242, "400079"),
    ("Kanjurmarg", 19.1314, 72.9358, "400078"),
    ("Bhandup West", 19.1474, 72.9351, "400078"),
    ("Mulund West", 19.1742, 72.9425, "400080"),
    ("Ghatkopar West", 19.0863, 72.9089, "400086"),
    ("Ghatkopar East", 19.0871, 72.9171, "400077"),
    ("Vidyavihar", 19.0742, 72.8990, "400077"),
    ("Kurla West", 19.0708, 72.8830, "400070"),
    ("Bandra Kurla Complex", 19.0667, 72.8696, "400051"),
    ("Bandra East", 19.0590, 72.8404, "400051"),
    ("Marol", 19.1192, 72.8843, "400059"),
    ("Saki Naka", 19.1085, 72.8889, "400072"),
    ("Chakala", 19.1108, 72.8589, "400099"),
    ("Versova", 19.1316, 72.8202, "400061"),
    ("Lokhandwala", 19.1303, 72.8295, "400053"),
    ("Oshiwara", 19.1532, 72.8332, "400102"),
    ("Goregaon West", 19.1647, 72.8392, "400062"),
    ("Aarey Colony", 19.1665, 72.8723, "400065"),
    ("Mira Road", 19.2841, 72.8703, "400107"),
    ("Dahisar West", 19.249, 72.857, "400068"),
    ("Magathane", 19.218, 72.866, "400066"),
    ("Charkop", 19.227, 72.821, "400067"),
]


# ---------------------------------------------------------------------------
# EXTRA STORE TEMPLATES (81 → STORES total 90) + matching owner profiles
# Seller indices 10..90, mapping to TEST_USERS extra slots in dev_seed.py.
# ---------------------------------------------------------------------------

_STORE_NAME_PREFIXES = [
    "Shree", "Krishna", "Sai", "Laxmi", "Ganesh", "Om", "Jai", "Aastha",
    "Mahalaxmi", "Tirupati", "Balaji", "Annapurna", "Sundar", "Jyoti",
    "Royal", "Modern", "Classic", "Prime", "Heritage", "Star", "Apna",
    "Daily", "Quick", "Fresh", "Mumbai", "Mahanagar", "Coastal", "Local",
    "Smart", "Express", "Galaxy", "Sunshine", "Greenline", "Bluewave",
]
_STORE_NAME_SUFFIXES_BY_SERVICE: dict[str, list[str]] = {
    "grocery": ["Kirana", "General Store", "Supermart", "Provisions", "Bazaar", "Fresh Market"],
    "electronics": ["Electronics", "Digital Store", "Tech Hub", "Gadget Zone", "Electronix", "Mart"],
    "pharmacy": ["Pharmacy", "Medicos", "Drug Store", "Health Mart", "Chemist", "MediCare"],
    "food": ["Kitchen", "Bistro", "Diner", "Eats", "Foodhall", "Cafe"],
    "bakery": ["Bakery", "Patisserie", "Bake Shop", "Cake House", "Bakers", "Confectionery"],
    "meat-seafood": ["Meat Shop", "Butchers", "Seafood Mart", "Fresh Cuts", "Coastal Catch", "Protein House"],
    "beauty": ["Beauty Store", "Cosmetics", "Glow Studio", "Beauty Hub", "Salon Shop", "Glam Bar"],
    "stationery": ["Stationers", "Book Depot", "Stationery", "Paperhouse", "Pen House", "Book Mart"],
    "pet-supplies": ["Pet Shop", "Pet Mart", "Pet Care", "Pet Hub", "Pawfect", "Animal Store"],
    "home-kitchen": ["Home Mart", "Kitchen Store", "House Hold", "Home Hub", "Decor House", "Home Depot"],
    "flowers-plants": ["Flowers", "Garden Center", "Plant House", "Florist", "Greenery", "Bloom Studio"],
    "sports-fitness": ["Sports Hub", "Fitness Store", "Sportiva", "Gym Mart", "Active Life", "Sports House"],
}
_ALL_SERVICE_SLUGS = [
    "grocery", "electronics", "pharmacy", "food", "bakery", "meat-seafood",
    "beauty", "stationery", "pet-supplies", "home-kitchen", "flowers-plants",
    "sports-fitness",
]


def _gen_store_name(seller_idx: int, primary_service: str) -> str:
    prefix = _STORE_NAME_PREFIXES[seller_idx % len(_STORE_NAME_PREFIXES)]
    suffixes = _STORE_NAME_SUFFIXES_BY_SERVICE[primary_service]
    suffix = suffixes[seller_idx % len(suffixes)]
    return f"{prefix} {suffix} #{seller_idx}"


def _generate_extra_stores_and_owners() -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    stores: list[dict[str, Any]] = []
    owners: list[dict[str, Any]] = []
    radii = [2.0, 3.0, 5.0, 8.0, 10.0, 15.0]
    for offset_idx, seller_idx in enumerate(range(10, 91)):
        nbh_name, nbh_lat, nbh_lng, pincode = MUMBAI_NEIGHBORHOODS[
            offset_idx % len(MUMBAI_NEIGHBORHOODS)
        ]
        lat = nbh_lat + _RNG.uniform(-0.005, 0.005)
        lng = nbh_lng + _RNG.uniform(-0.005, 0.005)
        primary = _ALL_SERVICE_SLUGS[seller_idx % len(_ALL_SERVICE_SLUGS)]
        extra_pool = [s for s in _ALL_SERVICE_SLUGS if s != primary]
        extra_count = _RNG.choice([0, 1, 1, 2])
        service_slugs = [primary, *_RNG.sample(extra_pool, k=extra_count)]
        radius = _RNG.choice(radii)
        name = _gen_store_name(seller_idx, primary)
        house_no = _RNG.randint(1, 999)
        line1 = f"Shop {house_no}"
        store = {
            "name": name,
            "seller_idx": seller_idx,
            # service_slugs is consumed by generate_extra_inventories so each
            # store's inventory is restricted to products under services the
            # owner actually offers. Without it, the cart-add 409s on
            # service_unavailable / service_mismatch.
            "service_slugs": service_slugs,
            "address_line1": line1,
            "address_line2": nbh_name,
            "landmark": None,
            "city": "Mumbai",
            "state": "Maharashtra",
            "pincode": pincode,
            "country": "India",
            "latitude": round(lat, 6),
            "longitude": round(lng, 6),
            "place_id": None,
            "location_source": "pin",
            "delivery_radius_km": radius,
            "pin_confirmed": True,
        }
        stores.append(store)
        owner_full_name = f"Seller {seller_idx:03d} Patil"
        owner = {
            "email": f"seller{seller_idx}@khanabazaar.dev",
            "full_name": owner_full_name,
            "business_name": name,
            "service_slugs": service_slugs,
            "phone": f"+9198111{(seller_idx + 10):05d}",
            "gst_number": f"27{seller_idx:08d}A{seller_idx % 10}Z{seller_idx % 10}",
            "fssai_license": f"{10000000000000 + seller_idx * 13}",
            "bank_account_number": f"{50100200000000 + seller_idx * 17}",
            "bank_ifsc": _RNG.choice(["HDFC", "ICIC", "SBIN", "AXIS", "KKBK", "PNBN"]) + f"000{seller_idx:04d}",
            "status": VerificationStatus.Approved,
            "rejection_reason": None,
        }
        owners.append(owner)
    return stores, owners


EXTRA_STORES, EXTRA_STORE_OWNER_PROFILES = _generate_extra_stores_and_owners()


# ---------------------------------------------------------------------------
# EXTRA CUSTOMERS (9 → CUSTOMERS total 10; anchor Priya Verma stays at idx 0)
# Each carries 5 addresses (45 total addresses across the 9 extras).
# ---------------------------------------------------------------------------

_CUSTOMER_FIRST_NAMES = [
    "Aarav", "Vivaan", "Ananya", "Aditi", "Kabir", "Aisha", "Rohan",
    "Diya", "Karan",
]
_CUSTOMER_LAST_NAMES = [
    "Iyer", "Khan", "Singh", "Reddy", "Joshi", "Pillai", "Desai",
    "Kapoor", "Nair",
]
_ADDRESS_LABELS = ["Home", "Office", "Parents", "Friend's Place", "Weekend"]


def _gen_address(label: str, is_default: bool, nbh_idx: int) -> dict[str, Any]:
    nbh_name, lat, lng, pincode = MUMBAI_NEIGHBORHOODS[nbh_idx % len(MUMBAI_NEIGHBORHOODS)]
    lat += _RNG.uniform(-0.004, 0.004)
    lng += _RNG.uniform(-0.004, 0.004)
    return {
        "label": label,
        "is_default": is_default,
        "address_line1": f"Flat {_RNG.randint(101, 1899)}",
        "address_line2": nbh_name,
        "landmark": None,
        "city": "Mumbai",
        "state": "Maharashtra",
        "pincode": pincode,
        "country": "India",
        "latitude": round(lat, 6),
        "longitude": round(lng, 6),
        "place_id": None,
        "location_source": "pin",
    }


def _generate_extra_customers() -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for i in range(9):
        first = _CUSTOMER_FIRST_NAMES[i]
        last = _CUSTOMER_LAST_NAMES[i]
        base_nbh = i * 5
        addresses = [
            _gen_address(_ADDRESS_LABELS[a], a == 0, base_nbh + a)
            for a in range(5)
        ]
        out.append({
            "email": f"customer{i + 2}@khanabazaar.dev",
            "full_name": f"{first} {last}",
            "phone": f"+919812110{(i + 2):03d}",
            "addresses": addresses,
        })
    return out


EXTRA_CUSTOMERS: list[dict[str, Any]] = _generate_extra_customers()


# ---------------------------------------------------------------------------
# EXTRA APPLICATIONS (27 → APPLICATIONS total 30; 9 each pending/approved/rejected)
# ---------------------------------------------------------------------------

_APPLICANT_FIRST_NAMES = [
    "Rishabh", "Tanvi", "Manish", "Sneha", "Ishaan", "Komal", "Yash",
    "Pallavi", "Devansh", "Riya", "Kunal", "Mira", "Aakash", "Shruti",
    "Nikhil", "Anushka", "Varun", "Priyanka", "Aman", "Megha", "Saurabh",
    "Tarun", "Bhavna", "Mehul", "Ritu", "Sahil", "Aaradhya",
]
_APPLICANT_LAST_NAMES = [
    "Sharma", "Verma", "Khanna", "Pillai", "Joshi", "Iyer", "Rao",
    "Sen", "Bose", "Chatterjee", "Mukherjee", "Banerjee", "Gandhi",
    "Patel", "Shah", "Mehta", "Trivedi", "Saxena", "Goyal", "Mittal",
    "Sodhi", "Khan", "Hussain", "Pandey", "Pandit", "Bhatia", "Aggarwal",
]
_BUSINESS_TYPES = [
    ("Fresh Kirana", "grocery"),
    ("Mart", "grocery"),
    ("Pharmacy", "pharmacy"),
    ("Medicos", "pharmacy"),
    ("Electronics", "electronics"),
    ("Bakery", "bakery"),
    ("Kitchen", "food"),
    ("Pet Care", "pet-supplies"),
    ("Beauty Studio", "beauty"),
]
_APP_CITIES_STATES = [
    ("Mumbai", "Maharashtra", "400001"),
    ("Pune", "Maharashtra", "411001"),
    ("Bengaluru", "Karnataka", "560001"),
    ("Delhi", "Delhi", "110001"),
    ("Hyderabad", "Telangana", "500001"),
    ("Chennai", "Tamil Nadu", "600001"),
    ("Kolkata", "West Bengal", "700001"),
    ("Ahmedabad", "Gujarat", "380001"),
    ("Jaipur", "Rajasthan", "302001"),
]
_REJECTION_REASONS = [
    "GST number does not match business address on record. Please update and resubmit.",
    "FSSAI license is expired. Renew and submit fresh certificate.",
    "Bank account verification failed. Re-submit with corrected IFSC.",
    "Business address could not be verified at provided pincode.",
    "Required identity documents missing. Re-upload and resubmit.",
]


def _generate_extra_applications() -> list[dict[str, Any]]:
    statuses = (
        [VerificationStatus.Pending] * 9
        + [VerificationStatus.Approved] * 9
        + [VerificationStatus.Rejected] * 9
    )
    out: list[dict[str, Any]] = []
    for i, status in enumerate(statuses):
        first = _APPLICANT_FIRST_NAMES[i]
        last = _APPLICANT_LAST_NAMES[i]
        biz_suffix, biz_service = _BUSINESS_TYPES[i % len(_BUSINESS_TYPES)]
        city, state, pincode = _APP_CITIES_STATES[i % len(_APP_CITIES_STATES)]
        status_token = {
            VerificationStatus.Pending: "pending",
            VerificationStatus.Approved: "approved",
            VerificationStatus.Rejected: "rejected",
        }[status]
        out.append({
            "email": f"{status_token}{i + 1}.seller@khanabazaar.dev",
            "full_name": f"{first} {last}",
            "business_name": f"{first} {biz_suffix}",
            "service_slugs": [biz_service],
            "address_line1": f"Shop {_RNG.randint(1, 999)}",
            "address_line2": _RNG.choice(["Main Road", "Market Lane", "Sector 4", "Phase 2", "MG Road"]),
            "landmark": None,
            "city": city,
            "state": state,
            "pincode": pincode,
            "country": "India",
            "latitude": None,
            "longitude": None,
            "phone": f"+91981234{(7700 + i):04d}",
            "gst_number": f"29{i:06d}Z{i % 10}Z{i % 10}Z{i % 10}",
            "fssai_license": f"{20000000000000 + i * 11}",
            "bank_account_number": f"{60100200000000 + i * 19}",
            "bank_ifsc": _RNG.choice(["HDFC", "ICIC", "SBIN", "AXIS"]) + f"0009{i:03d}",
            "status": status,
            "rejection_reason": _REJECTION_REASONS[i % len(_REJECTION_REASONS)] if status == VerificationStatus.Rejected else None,
        })
    return out


EXTRA_APPLICATIONS: list[dict[str, Any]] = _generate_extra_applications()


# ---------------------------------------------------------------------------
# EXTRA INVENTORIES — generated per extra store. Each store gets 30–50 SKUs
# from products matching its service_slugs. Price jittered ±20% around
# base_price; stock 0..60 with ~8% out-of-stock rows for QA coverage.
# ---------------------------------------------------------------------------


def _build_service_to_subcat_slugs(
    services: list[dict[str, Any]],
    categories: list[dict[str, Any]],
    subcategories: list[dict[str, Any]],
) -> dict[str, list[str]]:
    cat_to_service: dict[str, str] = {c["slug"]: c["service_slug"] for c in categories}
    out: dict[str, list[str]] = {s["slug"]: [] for s in services}
    for sub in subcategories:
        svc = cat_to_service.get(sub["category_slug"])
        if svc is not None:
            out[svc].append(sub["slug"])
    return out


def _build_subcat_to_product_slugs(products: list[dict[str, Any]]) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for p in products:
        out.setdefault(p["subcategory_slug"], []).append(p["slug"])
    return out


def generate_extra_inventories(
    *,
    all_services: list[dict[str, Any]],
    all_categories: list[dict[str, Any]],
    all_subcategories: list[dict[str, Any]],
    all_products: list[dict[str, Any]],
    anchor_store_count: int,
) -> list[tuple[int, str, float, int]]:
    """Build inventory rows for each extra store. Called from dev_seed.py
    after SERVICES/CATEGORIES/SUBCATEGORIES/PRODUCTS are merged so the lookup
    maps cover both anchor + extra data."""
    svc_to_subs = _build_service_to_subcat_slugs(all_services, all_categories, all_subcategories)
    sub_to_prods = _build_subcat_to_product_slugs(all_products)
    base_price = {p["slug"]: float(p["base_price"]) for p in all_products}

    rows: list[tuple[int, str, float, int]] = []
    for offset, store in enumerate(EXTRA_STORES):
        store_idx = anchor_store_count + offset
        candidates: list[str] = []
        for svc in store.get("service_slugs", []) or []:
            for sub_slug in svc_to_subs.get(svc, []):
                candidates.extend(sub_to_prods.get(sub_slug, []))
        if not candidates:
            candidates = list(base_price.keys())
        target = min(_RNG.randint(30, 50), len(candidates))
        picks = _RNG.sample(candidates, k=target)
        for slug in picks:
            bp = base_price[slug]
            price = round(bp * _RNG.uniform(0.85, 1.20), 2)
            stock = 0 if _RNG.random() < 0.08 else _RNG.randint(3, 60)
            rows.append((store_idx, slug, price, stock))
    return rows


__all__ = [
    "EXTRA_SERVICES",
    "EXTRA_CATEGORIES",
    "EXTRA_SUBCATEGORIES",
    "EXTRA_PRODUCTS",
    "EXTRA_STORES",
    "EXTRA_STORE_OWNER_PROFILES",
    "EXTRA_CUSTOMERS",
    "EXTRA_APPLICATIONS",
    "MUMBAI_NEIGHBORHOODS",
    "generate_extra_inventories",
]



