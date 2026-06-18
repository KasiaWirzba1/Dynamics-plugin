#!/bin/bash
set -e
PROJECT=${1:-1IGD}
cd ~/.dynamics/$PROJECT
GMX=/usr/bin/gmx

# Krok 1: pdb2gmx - konwersja PDB (6 = AMBER99SB-ILDN)
echo "6" | $GMX pdb2gmx -f $PROJECT.pdb -o $PROJECT.gro -p $PROJECT.top -water tip3p 2>&1

# Krok 2: editconf - pudełko symulacyjne
$GMX editconf -f $PROJECT.gro -o ${PROJECT}1.gro -c -d 1.0 -bt triclinic 2>&1

# Krok 3: solvate - wypełnienie wodą
$GMX solvate -cp ${PROJECT}1.gro -cs spc216.gro -o ${PROJECT}_solv.gro -p $PROJECT.top 2>&1

# Krok 4: grompp + genion - dodanie jonów
$GMX grompp -f em.mdp -c ${PROJECT}_solv.gro -o ${PROJECT}_ions.tpr -p $PROJECT.top -maxwarn 2 2>&1
echo "13" | $GMX genion -s ${PROJECT}_ions.tpr -o ${PROJECT}_b4em.gro -neutral -p $PROJECT.top 2>&1

# Krok 5: minimalizacja energii
$GMX grompp -f em -c ${PROJECT}_b4em -p $PROJECT -o ${PROJECT}_em -maxwarn 2 2>&1
$GMX mdrun -nice 4 -s ${PROJECT}_em -o ${PROJECT}_em -c ${PROJECT}_b4pr -v 2>&1

# Krok 6: Position Restrained MD
$GMX grompp -f pr -c ${PROJECT}_b4pr -r ${PROJECT}_b4pr -p $PROJECT -o ${PROJECT}_pr -maxwarn 2 2>&1
$GMX mdrun -nice 4 -s ${PROJECT}_pr -o ${PROJECT}_pr -c ${PROJECT}_b4md -v 2>&1

# Krok 7: właściwa symulacja MD
$GMX grompp -f md -c ${PROJECT}_b4md -p $PROJECT -o ${PROJECT}_md -maxwarn 2 2>&1
$GMX mdrun -nice 4 -s ${PROJECT}_md -o ${PROJECT}_md -c ${PROJECT}_after_md -v 2>&1

# Krok 8: konwersja wyników
echo "0" | $GMX trjconv -f ${PROJECT}_md.trr -s ${PROJECT}_md.tpr -o ${PROJECT}_multimodel.pdb -pbc mol 2>&1

echo "SIMULATION COMPLETE"
