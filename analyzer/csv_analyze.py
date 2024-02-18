import csv

with open("lichess_db_puzzle.csv") as file:
    csv_reader = csv.reader(file)
    header = next(csv_reader)
    max_num_moves = 0
    for row in csv_reader:
        num_moves = len(row[2].split(' '))
        if num_moves > max_num_moves:
            max_num_moves = num_moves
            print(num_moves, row[0])
    print(max_num_moves)