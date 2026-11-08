import pandas as pd

armor = pd.read_csv('./data/csv/armor.csv')

shield = armor[
    armor['name'] == 'Vortex Shield'
].iloc[0]

shield_min = int(shield['mindam'])
shield_max = int(shield['maxdam'])

print(shield_min, shield_max)