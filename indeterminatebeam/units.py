"""Module to contain conversion from units to SI units"""

# the number in the key represents the number to multiply the
# the value by such that it becomes the SI unit

mm = 0.001
cm = 0.01
m = 1

N = 1
kN = 1000

METRIC_UNITS = {
'length': {'mm':mm, 'cm':cm, 'm':m},
'force': {'N':N, 'kN':kN},
'moment': {'N.mm':N*mm, 'kN.mm':kN*mm, 'N.m':N*m, 'kN.m':kN*m},
'distributed': {'N/mm':N/mm, 'kN/mm': kN/mm, 'N/m':N/m, 'kN/m':kN/m},
'stiffness': {'N/mm':N/mm, 'kN/mm': kN/mm, 'N/m':N/m, 'kN/m':kN/m},
'A': {'mm2':mm**2, 'cm2':cm**2, 'm2':m**2},
"E": {'Pa':N/(m**2), 'kPa':kN/(m**2), 'MPa':N/(mm**2)},
'I': {'mm4':mm**4, 'cm4':cm**4, 'm4':m**4},
'deflection': {'mm':mm, 'cm':cm, 'm':m},
}

inch = 0.0254
ft = 0.3048
lbf = 4.4482216
kip = 4448.2216

IMPERIAL_UNITS = {
'length': {'in':inch,'ft':ft},
'force': {'lbf':lbf,'kip':kip},
'moment': {'lbf.ft':lbf*ft, 'kip.ft':kip*ft, 'lbf.in':lbf*inch, 'kip.in':kip*inch},
'distributed': {'kip/ft':kip/ft, 'kip/in': kip/inch, 'lbf/ft':lbf/ft, 'lbf/in':lbf/inch},
'stiffness': {'kip/ft':kip/ft, 'kip/in': kip/inch, 'lbf/ft':lbf/ft, 'lbf/in':lbf/inch},
'A': {'in2':inch**2, 'ft2':ft**2},
"E": {'kip/in2':kip/(inch**2), 'kip/ft2':kip/(ft**2), 'lbf/in2':lbf/(inch**2),'lbf/ft2':lbf/(ft**2)},
'I': {'in4':(inch**4), 'ft4':(ft**4)},
'deflection': {'in':inch, 'ft':ft},
}

UNIT_KEYS = [k for k in METRIC_UNITS.keys()]
UNIT_VALUES = {}

for a in UNIT_KEYS:
    UNIT_VALUES[a] = [u for u in METRIC_UNITS[a].keys()]
    UNIT_VALUES[a] += [u for u in IMPERIAL_UNITS[a].keys()]