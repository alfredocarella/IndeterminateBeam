"""Main module that contains the main class Beam, and auxiliary classes
Support, PointLoadH, PointLoadV, DistributedLoadH, and DistributedLoadV,
PointLoad, PointTorque and TrapezoidalLoad.

Example
-------
>>> beam = Beam(6)
>>> a = Support()
>>> c = Support(6,(0,1,0))
>>> beam.add_supports(a,c)
>>> beam.add_loads(PointLoadV(-15,3))
>>> beam.analyse()
>>> beam.plot()
"""

from collections import namedtuple
from copy import deepcopy
import numpy as np
import os
from sympy import (integrate, lambdify, Piecewise, sympify, symbols, 
                   linsolve, sin, cos, oo, SingularityFunction)
from sympy.abc import x
from math import radians
from data_validation import (assert_number, assert_positive_number,
                             assert_strictly_positive_number, assert_length)
from plotly_drawing_aid import (
    draw_line, draw_arrowhead, draw_arrow, draw_support_triangle,
    draw_support_rectangle, draw_moment, draw_force, draw_load_hoverlabel,
    draw_reaction_hoverlabel, draw_support_hoverlabel, draw_support_rollers,
    draw_support_spring, draw_support
    )
from plotly.subplots import make_subplots
import plotly.graph_objects as go

import time


class Support:
    """
    A class to represent a support.

    Attributes:
    -------------
        _position: float
            x coordinate of support on a beam (default 0)
        _stiffness: tuple of 3 floats or infinity
            stiffness K (kN/mm) for movement in x, y and bending, oo
            represents infinity in sympy and means a completely fixed
            conventional support, and 0 means free to move.
        _DOF : tuple of 3 booleans
            Degrees of freedom that are restraint on a beam for
            movement in x, y and bending, 1 represents that a reaction
            force exists and 0 represents free (default (1,1,1))
        _fixed: tuple of 3 booleans
            Degrees of freedom that are completely fixed on a beam for
            movement in x, y and bending, 1 represents fixed and 0
            represents free or spring  (default (1,1,1))
        _id : positive number
            id assigned when support associated with Beam object, to
            help remove supports.

    Examples
    --------
    # Creates a fixed suppot at location 0
    >>> Support(0, (1,1,1))
    # Creates a pinned support at location 5
    >>> Support(5, (1,1,0))
    # Creates a roller support at location 5.54
    >>> Support(5.54, (0,1,0))
    # Creates a y direction spring support at location 7.5
    >>> Support(7.5, (0,1,0), ky = 5)
    """

    def __init__(self, coord=0, fixed=(1, 1, 1), kx=None, ky=None):
        """
        Constructs all the necessary attributes for the Support object.

        Parameters:
        -----------
        coord: float
            x coordinate of support on a beam (default 0)
            (default not 0.0 due to a float precision error that
            previously occured)
        fixed: tuple of 3 booleans
            Degrees of freedom that are fixed on a beam for movement in
            x, y and bending, 1 represents fixed and 0 represents free
            (default (1,1,1))
        kx :
            stiffness of x support (kN/mm), if set will overide the
            value placed in the fixed tuple. (default = None)
        ky : (positive number)
            stiffness of y support (kN/mm), if set will overide the
            value placed in the fixed tuple. (default = None)
        """
        # input validation
        assert_positive_number(coord, 'coordinate')

        if kx:
            assert_positive_number(kx, 'kx')
        if ky:
            assert_positive_number(ky, 'ky')

        for a in fixed:
            if a not in [0, 1]:
                raise ValueError(
                    "The provided fixed parameter, must be a tuple of \
                    booleans of length 3"
                )
        if len(fixed) != 3:
            raise ValueError(
                "The provided fixed parameter, must be a tuple of \
                booleans of length 3"
            )

        # Spring representation, set rigid to infinity instead of 1
        self._stiffness = [oo if a else 0 for a in fixed]

        # If kx or ky has been included override oo value
        if kx:
            self._stiffness[0] = kx
        if ky:
            self._stiffness[1] = ky

        # Assign properties for support
        self._DOF = [int(bool(e)) for e in self._stiffness]
        self._fixed = [
            int(bool(e)) if e == oo else 0 for e in self._stiffness
        ]
        self._position = coord
        self._id = None

    def __str__(self):
        return f"""--------------------------------
        id = {self._id}
        position = {float(self._position)}
        Stiffness_x = {self._stiffness[0]}
        Stiffness_y = {self._stiffness[1]}
        Stiffness_M = {self._stiffness[2]} """

    def __repr__(self):
        if self._id:
            return f"<support, id = {self._id}>"
        return "<Support>"

class PointTorque:
    """Point clockwise torque, described by a tuple of floats:
    (torque, coord).

    Parameters:
    -----------
    torque: float
        Torque in kN.m
    coord: float
        x coordinate of torque on beam

    Examples
    --------
    # 30 kN·m (clockwise) torque at x=4 m
    >>> motor_torque = PointTorque(30, 4)
    """

    
    def __init__(self, torque = 0, coord=0):
        assert_number(torque, 'torque')
        assert_positive_number(coord, 'coordinate')
        
        self._x = 0
        self._y = torque * SingularityFunction(x, coord, -1)

class PointLoad:
    """Point load described by a tuple of floats: (force, coord, angle).

    Parameters:
    -----------
    Force: float
        Force in kN
    coord: float
        x coordinate of load on beam
    angle: float
        angle of point load where:
        - 0 degrees is purely horizontal +ve
        - 90 degrees is purely vertical +ve
        - 180 degrees is purely horizontal -ve of force sign specified.


    Examples
    --------
    # 10 kN towards the right at x=9 m
    >>> external_force = PointLoad(10, 9, 90)
    # 30 kN downwards at x=3 m
    >>> external_force = PointLoad(-30, 3, 0)
    >>> external_force
    PointLoad(force=-30, coord=3, angle=0)
    """
    
    def __init__(self, force = 0, coord=0, angle=0):
        assert_number(force, 'force')
        assert_positive_number(coord, 'coordinate')
        assert_number(angle, 'angle')

        force_x = force * cos(radians(angle)).evalf(8)
        force_y = force * sin(radians(angle)).evalf(8)

        if abs(round(force_x,5)) > 0:
            self._x = force_x * SingularityFunction(x, coord, -1)
        else: 
            self._x = 0
        
        if abs(round(force_y,5)) > 0:
            self._y = force_y * SingularityFunction(x, coord, -1)
        else: 
            self._y = 0

class PointLoadV(PointLoad):
    def __init__(self, force = 0, coord = 0):
        super().__init__(force,coord,angle=90)

class PointLoadH(PointLoad):
    def __init__(self, force = 0, coord = 0):
        super().__init__(force,coord,angle=0)


class DistributedLoad:
    """Distributed load, described by its functional form, application 
    interval and the angle of the load relative to the beam.

    Parameters:
    -----------
    expr: sympy expression
        Sympy expression of the distributed load function expressed
        using variable x which represents the beam x-coordinate.
        Requires quotation marks around expression.
    span: tuple of floats
        A tuple containing the starting and ending coordinate that
         the function is applied to.
    angle: float
        angle of point load where:
        - 0 degrees is purely horizontal +ve
        - 90 degrees is purely vertical +ve
        - 180 degrees is purely horizontal -ve of force sign specified.
    Examples
    --------
    # Linearly growing load for 0<x<2 m
    >>> snow_load = DistributedLoad("10*x+5", (0, 2),90)
    """

    def __init__(self, expr, span =(0, 0), angle = 0):
        try:
            expr = sympify(expr)
        except:
            print("Can not convert expression to sympy function. \
            Function should only contain variable x, should be \
            encapsulated by quotations, and should have * between x \
            and coefficients i.e 2 * x rather than 2x")
        
        # Validate span input
        assert_length(span, 2, 'span')
        assert_positive_number(span[0], 'span start')
        assert_strictly_positive_number(span[1]-span[0] 'span start minus span end')

        # validate angle input
        assert_number(angle, 'angle')

        force_x = cos(radians(angle)).evalf(10)
        force_y = sin(radians(angle)).evalf(10)

        if abs(round(force_x,8)) > 0:
            self._x = force_x * expr
        else: 
            self._x = 0
        
        if abs(round(force_y,8)) > 0:
            self._y = force_y * expr
        else: 
            self._y = 0

class DistributedLoadV(DistributedLoad):
    def __init__(self, expr = 0, span = (0,0)):
        super().__init__(expr, span, angle=90)

class DistributedLoadH(DistributedLoad):
    def __init__(self, expr = 0, span = (0,0)):
        super().__init__(expr, span, angle=0)

class UDL:
    
    def __init__(self, force = 0, span =(0, 0), angle = 0):
        
        # Validate span input
        assert_length(span, 2, 'span')
        assert_positive_number(span[0], 'span start')
        assert_strictly_positive_number(span[1]-span[0] 'span start minus span end')

        # validate angle input
        assert_number(angle, 'angle')

        force_x = force * cos(radians(angle)).evalf(8)
        force_y = force * sin(radians(angle)).evalf(8)

        if abs(round(force_x,5)) > 0:
            self._x = force_x * (
                SingularityFunction(x, span[0], 0) - SingularityFunction(x, span[1], 0)
                )
        else: 
            self._x = 0
        
        if abs(round(force_y,5)) > 0:
            self._y = force_y * (
                SingularityFunction(x, span[0], 0) - SingularityFunction(x, span[1], 0)
                )
        else: 
            self._y = 0

class TrapezoidalLoad:

    def __init__(self, force = (0,0), span =(0, 0), angle = 0):
        # Validate force input
        assert_length(force, 2, 'force')

        # check if UDL (not sure if this code will work properly)
        if force[0] == force [1]:
            return UDL(force[0], span, angle)

        # Validate span input
        assert_length(span, 2, 'span')
        assert_positive_number(span[0], 'span start')
        assert_strictly_positive_number(span[1]-span[0] 'span start minus span end')

        # validate angle input
        assert_number(angle, 'angle')

        #turn trapezoid into a triangle + rectangle
        UDL_component = UDL(force[0], span, angle)

        # express values for triangular load distribution
        xa, xb = span[0], span[1]
        a, b = 0, force[1] - force[0]
        slope = b / (span[1] - span[0])

        force_x = cos(radians(angle)).evalf(10)
        force_y = sin(radians(angle)).evalf(10)

        triangular_component = sum([
            + slope * SingularityFunction(x, xa, 1),
            - b * SingularityFunction(x, xb, 0),
            - slope * SingularityFunction(x, xb, 1),
        ])

        if abs(round(force_x,8)) > 0:
            self._x = UDL_component._x + force_x * triangular_component
        else: 
            self._x = 0
        
        if abs(round(force_y,8)) > 0:
            self._y = UDL_component._y + force_y * triangular_component
        else: 
            self._y = 0


class Beam:
    """
    Represents a one-dimensional beam that can take axial and
    tangential loads.

    Attributes
    --------------
    _x0 :float
        Left end coordinate of beam. This module always takes this
        value as 0.
    _x1 :float
        Right end coordinate of beam. This module always takes this
        to be the same as the beam span.

    _loads: list
        list of load objects associated with the beam
    _distributed_forces_x: list
        list of distributed forces implemented as piecewise functions
    _distributed_forces_y:
        list of distributed forces implemented as piecewise functions

    _normal_forces: sympy piecewise function
        A sympy function representing the internal axial force as a
        function of x.
    _shear_forces: sympy piecewise function
        A sympy function representing the internal shear force as a
        function of x.
    _bending_moments: sympy piecewise function
        A sympy function representing the internal bending moments
        as a function of x.

    _query: list
        A list containing x coordinates that are to have values
        explicitly written on graphs.
    _supports: list
        A list of support objects associated with the beam.
    _reactions: dictionary of lists
        A dictionary with keys for support positions. Each key is
        associated with a list of forces of the form ['x','y','m']

    _E: float
        Young's Modulus of the beam (N/mm2 or MPa)
    _I: float
        Second Moment of Area of the beam (mm4)
    _A: float
        Cross-sectional area of the beam (mm2)

    Notes
    -----
    * The default units for length, force and bending moment (torque)
      are in kN and m (m, kN, kN·m)
    * The default units for beam properties (E, I, A) are in N and mm
      (N/mm2, mm4, mm2)
    * The default unit for spring supports is kN/mm
    * Default properties are for a 150UB18.0 steel beam.
    """

    def __init__(self, span: float = 10, E=2 * 10**5, I=9.05 * 10**6,
                 A=2300):
        """Initializes a Beam object of a given length.

        Parameters
        ----------
        span : float
            Length of the beam span. Must be positive, and the pinned
            and rolling supports can only be placed within this span.
            The default value is 10.
        E: float
            Youngs modulus for the beam. The default value is
            200 000 MPa, which is the youngs modulus for steel.
        I: float
            Second moment of area for the beam about the z axis.
            The default value is 905 000 000 mm4.
        A: float
            Cross-sectional area for the beam about the z axis.
            The default value is 2300 mm4.
        """

        assert_strictly_positive_number(span, 'span')
        assert_strictly_positive_number(E, "Young's Modulus (E)")
        assert_strictly_positive_number(I, 'Second Moment of Area (I)')
        assert_strictly_positive_number(A, 'Area (A)')

        self._x0 = 0
        self._x1 = span

        self._loads = []
        self._distributed_forces_x = {}
        self._distributed_forces_y = {}

        self._normal_forces = []
        self._shear_forces = []
        self._bending_moments = []

        self._query = []
        self._supports = []
        self._reactions = {}

        self._E = E
        self._I = I
        self._A = A

    def add_loads(self, *loads):
        """Apply an arbitrary list of (point or distributed) loads
        to the beam.

        Parameters
        ----------
        loads : iterable
            An iterable containing DistributedLoad or PointLoad objects
            to be applied to the Beam object. Note that the load
            application point (or segment) must be within the Beam span.

        """
        # For every load validate that has correct values to fit the
        # beam such that no errors occur in analysis from the loads.
        # If load valid then add to self._loads.
        # Note: Have ignored distributedLoadH in this version.
        for load in loads:
            if isinstance(load, (DistributedLoad, UDL, TrapezoidalLoad)):
                left, right = load

                if self._x0 > left or right > self._x1:
                    raise ValueError(
                        f"Coordinate {load[1]} for {str(load)} is not a point on beam."
                    )

            elif isinstance(load,(PointTorque, PointLoad)):
                coordinate = load[1]
                
                if self._x0 > coordinate or coordinate > self._x1:
                    raise ValueError(
                        f"Coordinate {coordinate} for {str(load)} is not a point on beam.")

            self._loads.append(load)


    def remove_loads(self, *loads, remove_all=False):
        """Remove an arbitrary list of (point- or distributed) loads
        from the beam.

        Parameters
        ----------
        loads : iterable
            An iterable containing DistributedLoad or PointLoad objects
            to be removed from the Beam object. If object not on beam
            then does nothing.
        remove_all: boolean
            If true all loads associated with beam will be removed.

        """
        # if remove all set, reintialize parameters
        if remove_all:
            self._loads = []
            return None

        # if individual loads check if associated with beam and if so
        # remove. 

        # Could be considered a bug that a user isnt notified
        # if a load isnt removed because it wasnt there. This might be
        # an issue if they dont properly recreate the load they were
        # trying to remove and dont notice that they didnt actually 
        # delete it.

        for load in loads:
            if load in self._loads:
                self._loads.remove(load)

    def add_supports(self, *supports):
        """Apply an arbitrary list of supports (Support objects) to the
        beam.

        Parameters
        ----------
        supports : iterable
            An iterable containing Support objects to be applied to 
            the Beam object. Note that the load application point 
            (or segment) must be within the Beam span.

        """

        # Check support valid then append to self._supports
        for support in supports:
            if not isinstance(support, Support):
                raise TypeError("support must be of type class Support")

            if (self._x0 > support._position) or (
                    support._position > self._x1):
                raise ValueError("Not a point on beam")

            if self._supports == []:
                self._supports.append(support)

            elif support._position not in [
                x._position for x in self._supports
            ]:
                self._supports.append(support)
            else:
                raise ValueError(
                    f"This coordinate {support._position} already has a support associated with it")

    def remove_supports(self, *supports, remove_all=False):
        """Remove an arbitrary list of supports (Support objects) from
        the beam.

        Parameters
        ----------
        *supports : iterable
            An iterable containing Support objects to be removed from
            the Beam object. If support not on beam then does nothing.
        remove_all: boolean
            If true all supports associated with beam will be removed.

        """
        if remove_all:
            self._supports = []
            return None

        for support in self._supports:
            if support in supports:
                self._supports.remove(support)
    
        # Could be considered a bug that a user isnt notified
        # if a support isnt removed because it wasnt there. This might 
        # be an issue if they dont properly recreate the support they 
        # were trying to remove and dont notice that they didnt actually 
        # delete it.

    def get_support_details(self):
        """Print out a readable summary of all supports on the beam. """

        print(f"There are {str(len(self._supports))} supports:", end='\n\n')
        for support in self._supports:
            print(support, end='\n\n')

    def check_determinancy(self):
        """Check the determinancy of the beam.

        Returns
        ---------
        int
            < 0 if the beam is unstable
            0 if the beam is statically determinate
            > 0 if the beam is statically indeterminate

        """

        unknowns = np.array([0, 0, 0])
        equations = 3

        # DOF has a 1 where a reaction force is returned, the sum of 
        # this list returns the number of unknowns associated with a 
        # particular support. If consider all supports then have total
        # number of unknowns to solve for.
        for support in self._supports:
            unknowns = np.array(support._DOF) + unknowns

        # If you dont have any horizontal loads then x equilibrium isnt
        # helpful to solve the beam
        if unknowns[0] == 0:
            equations -= 1
        
        # If you dont have any vertical loads then y equilibrium isnt
        # helpful to solve the beam
        if unknowns[1] == 0:
            equations -= 1

        unknowns = sum(unknowns)

        if unknowns == 0:
            return ValueError("No reaction forces exist")

        if unknowns < equations:
            return ValueError("Structure appears to be unstable")

        else:
            self._determinancy = (unknowns - equations)
            return (unknowns - equations)

    def analyse(self):
        """Solve the beam structure for reaction and internal forces  """

        x0, x1 = self._x0, self._x1

        
        unknowns_x = {a._position: [
            symbols("x_" + str(a._position)),
            a._stiffness[0]
        ]
            for a in self._supports if a._stiffness[0] != 0}
        unknowns_y = {a._position: [
            symbols("y_" + str(a._position)), a._stiffness[1]]
            for a in self._supports if a._stiffness[1] != 0}
        unknowns_m = {a._position: [symbols(
            "m_" + str(a._position)), a._stiffness[2]]
            for a in self._supports if a._stiffness[2] != 0}

        # grab the set of all the sympy unknowns for y and m and change
        # to a list, do same for x unknowns
        unknowns_ym = [a[0] for a in unknowns_y.values()] \
            + [a[0] for a in unknowns_m.values()]

        unknowns_xx = [a[0] for a in unknowns_x.values()]

        # Assert that there are enough supports. Even though it logically
        # works to have no x support if you have no x loading, it works
        # much better in the program and makes the code alot shorter to
        # just enforce that an x support is there, even when there is no
        # load.
        if len(unknowns_xx) < 1:
            raise ValueError(
                'You need at least one x restraint, even if there are \
                no x forces')

        if len(unknowns_ym) < 2:
            raise ValueError(
                'You need at least two y or m restraints, even if there \
                are no y or m forces')

        # locations where x reaction is and order, for indeterminate axial
        # determaintion
        x_0 = [a for a in unknowns_x.keys()]
        x_0.sort()

        # external reaction equations
        F_Rx = sum([load._x for load in self._loads]) \
            + sum([a[0] for a in unknowns_x.values()])

        F_Ry = sum([load._x for load in self._loads]) \
            + sum([a[0] for a in unknowns_y.values()])

        # moments taken at the left of the beam, anti-clockwise is positive
        M_R = sum(integrate(load._y * x, (x, x0, x1)) for load in self._loads) \
            + sum([a[0] for a in unknowns_m.values()])

        # internal beam equations
        C1, C2 = symbols('C1'), symbols('C2')
        unknowns_ym = unknowns_ym + [C1] + [C2]

        # normal forces is same concept as shear forces only no
        # distributed for now.
        N_i = sum(
            load[1]
            for load in self._distributed_forces_x.values()
        ) \
            + sum(
            self._effort_from_pointload(f)
            for f in self._point_loads_x()
        ) \
            + sum(
                self._effort_from_pointload(PointLoadH(v[0], p))
                for p, v in unknowns_x.items()
        )

        Nv_EA = sum(
                load[2]
                for load in self._distributed_forces_x.values()
            ) \
            + sum(
                integrate(
                    self._effort_from_pointload(f),
                    x
                )
                for f in self._point_loads_x()
            ) \
            + sum(
                integrate(
                    self._effort_from_pointload(
                        PointLoadH(v[0], p)),
                        x
                )
                for p, v in unknowns_x.items()
            )

        # shear forces, an internal force acting down would be considered
        # positive by adopted convention hence if the sum of forces on
        # the beam are all positive, our internal force would also be
        # positive due to difference in convention
        F_i = sum(
            load[1]
            for load in self._distributed_forces_y.values()
        ) \
            + sum(
                self._effort_from_pointload(f)
                for f in self._point_loads_y()
        ) \
            + sum(
                self._effort_from_pointload(PointLoadV(v[0], p))
                for p, v in unknowns_y.items()
        )

        # bending moments at internal point means we are now looking left
        # along the beam when we take our moments (vs when we did external
        # external reactions and we looked right). An anti-clockwise moment
        # is adopted as positive internally. Hence we need to consider a
        # postive for our shear forces and negative for our moments by
        # our sign convention
        M_i = sum(
            load[2]
            for load in self._distributed_forces_y.values()
        ) \
            + sum(
                integrate(self._effort_from_pointload(f), x)
                for f in self._point_loads_y()
        ) \
            + sum(
                integrate(self._effort_from_pointload(PointLoadV(v[0], p)), x)
                for p, v in unknowns_y.items()
        ) \
            - sum(
                self._effort_from_pointload(PointTorque(v[0], p))
                for p, v in unknowns_m.items()
        ) \
            - sum(
                self._effort_from_pointload(f)
                for f in self._point_torques()
        )

        # with respect to x, + constants but the constants are the M at fixed
        # supports

        dv_EI = sum(
            load[3]
            for load in self._distributed_forces_y.values()
        ) \
            + sum(
            integrate(self._effort_from_pointload(f), x, x)
            for f in self._point_loads_y()
        ) \
            + sum(
            integrate(self._effort_from_pointload(PointLoadV(v[0], p)), x, x)
            for p, v in unknowns_y.items()
        ) \
            - sum(
            integrate(self._effort_from_pointload(PointTorque(v[0], p)), x)
            for p, v in unknowns_m.items()
        ) \
            - sum(
            integrate(self._effort_from_pointload(f), x)
            for f in self._point_torques()
        ) \
            + C1

        v_EI = sum(
            load[4]
            for load in self._distributed_forces_y.values()
        ) \
            + sum(
            integrate(self._effort_from_pointload(f), x, x, x)
            for f in self._point_loads_y()
        ) \
            + sum(
            integrate(self._effort_from_pointload(PointLoadV(v[0], p)), x, x, x)
            for p, v in unknowns_y.items()
        ) \
            - sum(
            integrate(self._effort_from_pointload(PointTorque(v[0], p)), x, x)
            for p, v in unknowns_m.items()
        ) \
            - sum(
            integrate(self._effort_from_pointload(f), x, x)
            for f in self._point_torques()
        ) \
            + C1 * x + C2

        # equations , create a lsit fo equations
        equations_ym = [F_Ry, M_R]

        # at location that moment is restaint, the slope is known (to be 0,
        # since dont deal for rotational springs)
        for position in unknowns_m.keys():
            equations_ym.append(dv_EI.subs(x, position))

        # at location that y support is restaint the deflection is known (to be
        # F/k)
        for position in unknowns_y.keys():
            equations_ym.append(
                (v_EI.subs(x, position) * 10 ** 12 / (self._E * self._I))
                + (unknowns_y[position][0] / unknowns_y[position][1])
            )

        # equation for normal forces, only for indeterminate in x
        equations_xx = [F_Rx]

        # the extension of the beam will be equal to the spring
        # displacement on right minus spring displacment on left
        start_x = x_0[0]
        if len(x_0) > 1:
            # dont consider the starting point? only want to look between
            # supports and not at cantilever sections i think
            for position in x_0[1:]:
                equations_xx.append(
                    (Nv_EA.subs(x, position) - Nv_EA.subs(x, start_x))
                    * 10**3 / (self._E * self._A)
                    + unknowns_x[start_x][0] / unknowns_x[start_x][1]
                    # represents elongation displacment on right
                    - unknowns_x[position][0] / unknowns_x[position][1]
                )

        # compute analysis with linsolve
        solutions_ym = list(linsolve(equations_ym, unknowns_ym))[0]
        solutions_xx = list(linsolve(equations_xx, unknowns_xx))[0]

        solutions = [a for a in solutions_ym + solutions_xx]

        solution_dict = dict(zip(unknowns_ym + unknowns_xx, solutions))

        self._reactions = {a._position: [0, 0, 0] for a in self._supports}

        # substitue in value instead of variable in functions
        for var, ans in solution_dict.items():
            v_EI = v_EI.subs(var, ans)  # complete deflection equation
            M_i = M_i.subs(var, ans)  # complete moment equation
            F_i = F_i.subs(var, ans)  # complete shear force equation
            N_i = N_i.subs(var, ans)  # complete normal force equation
            Nv_EA = Nv_EA.subs(var,ans)

            # create self._reactions to allow for plotting of reaction
            # forces if wanted and for use with get_reaction method.
            if var not in [C1, C2]:
                vec, num = str(var).split('_')
                position = float(num)
                if vec == 'x':
                    i = 0
                elif vec == 'y':
                    i = 1
                else:
                    i = 2
                self._reactions[position][i] = float(round(ans, 5))

        # moment unit is kn.m, dv_EI kn.m2, v_EI Kn.m3 --> *10^3, *10^9
        # to get base units. EI unit is N/mm2 , mm4 --> N.mm2
        self._shear_forces = F_i
        self._bending_moments = M_i
        # a positive moment indicates a negative deflection, i thought??
        self._deflection_equation = v_EI * 10 ** 12 / (self._E * self._I)
        self._normal_forces = N_i
        # Nv_EI represents the beam elongation, to make displacement need to add initial
        # Comparatively v_EI is already the beam displacement and has a constant in it
        # (C2) that considers any intial displacement
        if unknowns_x[start_x][1] == oo:
            initial_displacement_x = 0
        else:
            initial_displacement_x = float(solutions_xx[0]  / unknowns_x[start_x][1])
        # in meters
        self._axial_deflection= Nv_EA * 10**3 / (self._E * self._A) \
            + initial_displacement_x / 10 ** 3 

    # SECTION - QUERY VALUE
    def get_reaction(self, x_coord, direction=None):
        """Find the reactions of a support at position x.

        Parameters
        ----------
        x_coord: float
            The x_coordinates on the beam to be substituted into the
            equation. List returned (if bools all false)
        direction: str ('x','y' or 'm')
            The direction of the reaction force to be returned.
            If not specified all are returned in a list.

        Returns
        --------
        int
            If direction is 'x', 'y', or 'm' will return an integer
            representing the reaction force of the support in that
            direction at location x_coord.
        list of ints
            If direction = None, will return a list of 3 integers,
            representing the reaction forces of the support ['x','y','m']
            at location x_coord.
        None
            If there is no support at the x coordinate specified.
        """

        if not self._reactions:
            print(
                "You must analyse the structure before calling this function"
            )

        assert_positive_number(x_coord, 'x coordinate')

        if x_coord not in self._reactions.keys():
            return None

        directions = ['x', 'y', 'm']

        if direction:
            if direction not in directions:
                raise ValueError(
                    "direction should be the value 'x', 'y' or 'm'")
            else:
                return self._reactions[x_coord][directions.index(direction)]
        else:
            return self._reactions[x_coord]

    # check if sym_func is the sum of the functions already in
    # plot_analytical

    def _get_query_value(self,x_coord,sym_func,return_max=False,
                         return_min=False,return_absmax=False):
        """Find the value of a function at position x_coord.

        Parameters
        ----------
        x_coord: list
            The x_coordinates on the beam to be substituted into the
            equation. List returned (if bools all false)
        sym_func: sympy function
            The function to be analysed
        return_max: bool
            return max value of function if true
        return_min: bool
            return minx value of function if true
        return_absmax: bool
            return absolute max value of function if true

        Returns
        --------
        int
            Max, min or absmax value of the sympy function depending
            on which parameters are set.
        list of ints
            If x-coordinate(s) are specfied value of sym_func at
            x-coordinate(s).

        Notes
        -----
        * Priority of query parameters is return_max, return_min,
          return_absmax, x_coord (if more than 1 of the parameters are
          specified).

        """

        if isinstance(sym_func, list):
            sym_func = sum(sym_func)
        func = lambdify(x, sym_func, "numpy")

        if 1 not in (return_absmax, return_max, return_min):
            if type(x_coord) == tuple:
                return [round(float(func(x_)), 3) for x_ in x_coord]
            else:
                return round(float(func(x_coord)), 3)

        # numpy array for x positions closely spaced (allow for graphing)
        # i think lambdify is needed to let the function work with numpy
        x_vec = np.linspace(self._x0, self._x1, int(1000))
        y_vec = np.array([func(t) for t in x_vec])
        min_ = float(y_vec.min())
        max_ = float(y_vec.max())

        if return_max:
            return round(max_, 3)
        elif return_min:
            return round(min_, 3)
        elif return_absmax:
            return round(max(abs(min_), max_), 3)

    def get_bending_moment(self,*x_coord, return_max=False,
                           return_min=False, return_absmax=False):
        """Find the bending moment(s) on the beam object.

        Parameters
        ----------
        x_coord: list
            The x_coordinates on the beam to be substituted into the
            equation. List returned (if bools all false)
        return_max: bool
            return max value of function if true
        return_min: bool
            return minx value of function if true
        return_absmax: bool
            return absolute max value of function if true

        Returns
        --------
        int
            Max, min or absmax value of the bending moment function
            depending on which parameters are set.
        list of ints
            If x-coordinate(s) are specfied value of the bending moment
            function at x-coordinate(s).

        Notes
        -----
        * Priority of query parameters is return_max, return_min,
          return_absmax, x_coord (if more than 1 of the parameters are
          specified).

        """

        return self._get_query_value(
            x_coord,
            sym_func=self._bending_moments,
            return_max=return_max,
            return_min=return_min,
            return_absmax=return_absmax
        )

    def get_shear_force(self, *x_coord, return_max=False, return_min=False,
                        return_absmax=False):
        """Find the shear force(s) on the beam object.

        Parameters
        ----------
        x_coord: list
            The x_coordinates on the beam to be substituted into the
            equation. List returned (if bools all false)
        return_max: bool
            return max value of function if true
        return_min: bool
            return minx value of function if true
        return_absmax: bool
            return absolute max value of function if true

        Returns
        --------
        int
            Max, min or absmax value of the shear force function
            depending on which parameters are set.
        list of ints
            If x-coordinate(s) are specfied value of the shear force
            function at x-coordinate(s).

        Notes
        -----
        * Priority of query parameters is return_max, return_min,
          return_absmax, x_coord (if more than 1 of the parameters are
          specified).

        """

        return self._get_query_value(
            x_coord,
            sym_func=self._shear_forces,
            return_max=return_max,
            return_min=return_min,
            return_absmax=return_absmax
        )

    def get_normal_force(self, *x_coord, return_max=False, return_min=False,
                         return_absmax=False):
        """Find the normal force(s) on the beam object.

        Parameters
        ----------
        x_coord: list
            The x_coordinates on the beam to be substituted into the
            equation. List returned (if bools all false)
        return_max: bool
            return max value of function if true
        return_min: bool
            return minx value of function if true
        return_absmax: bool
            return absolute max value of function if true

        Returns
        --------
        int
            Max, min or absmax value of the normal force function
            depending on which parameters are set.
        list of ints
            If x-coordinate(s) are specfied value of the normal force
            function at x-coordinate(s).

        Notes
        -----
        * Priority of query parameters is return_max, return_min,
          return_absmax, x_coord (if more than 1 of the parameters are
          specified).

        """
        return self._get_query_value(
            x_coord,
            sym_func=self._normal_forces,
            return_max=return_max,
            return_min=return_min,
            return_absmax=return_absmax
        )

    def get_deflection(self, *x_coord, return_max=False, return_min=False,
                       return_absmax=False):
        """Find the deflection(s) on the beam object.

        Parameters
        ----------
        x_coord: list
            The x_coordinates on the beam to be substituted into the
            equation. List returned (if bools all false)
        return_max: bool
            return max value of function if true
        return_min: bool
            return minx value of function if true
        return_absmax: bool
            return absolute max value of function if true

        Returns
        --------
        int
            Max, min or absmax value of the deflection function depending
            on which parameters are set.
        list of ints
            If x-coordinate(s) are specfied value of the deflection
            function at x-coordinate(s).

        Notes
        -----
        * Priority of query parameters is return_max, return_min,
          return_absmax, x_coord (if more than 1 of the parameters are
          specified).

        """

        return self._get_query_value(
            x_coord,
            sym_func=self._deflection_equation,
            return_max=return_max,
            return_min=return_min,
            return_absmax=return_absmax)

    def get_axial_deflection(self, *x_coord, return_max=False, return_min=False,
                       return_absmax=False):
        """Find the axial deflection(s) on the beam object.

        Parameters
        ----------
        x_coord: list
            The x_coordinates on the beam to be substituted into the
            equation. List returned (if bools all false)
        return_max: bool
            return max value of function if true
        return_min: bool
            return minx value of function if true
        return_absmax: bool
            return absolute max value of function if true

        Returns
        --------
        int
            Max, min or absmax value of the axial deflection function 
            depending on which parameters are set.
        list of ints
            If x-coordinate(s) are specfied value of the deflection
            function at x-coordinate(s).

        Notes
        -----
        * Priority of query parameters is return_max, return_min,
          return_absmax, x_coord (if more than 1 of the parameters are
          specified).

        """

        return self._get_query_value(
            x_coord,
            sym_func=self._axial_deflection,
            return_max=return_max,
            return_min=return_min,
            return_absmax=return_absmax)

    # SECTION - PLOTTING

    def add_query_points(self, *x_coords):
        """Document the forces on a beam at position x_coord when
        plotting.

        Parameters
        ----------
        x_coord: list
            The x_coordinates on the beam to be queried on plot.

        """
        for x_coord in x_coords:
            if self._x0 <= x_coord <= self._x1:
                self._query.append(x_coord)
            else:
                return ValueError("Not a point on beam")

    def remove_query_points(self, *x_coords, remove_all=False):
        """Remove a query point added by add_query_points function.

        Parameters
        ----------
        x_coord: list
            The x_coordinates on the beam to be removed from query on
            plot.
        remove_all: boolean
            if true all query points will be removed.

        """
        if remove_all:
            self._query = []
            return None

        for x_coord in x_coords:
            if x_coord in self._query:
                self._query.remove(x_coord)
            else:
                return ValueError("Not an existing query point on beam")

    def plot_beam_external(self):
        """A wrapper of several plotting functions that generates a
        single figure with 2 plots corresponding respectively to:

        - a schematic of the loaded beam
        - reaction force diagram

        Returns
        -------
        figure : `plotly.graph_objs._figure.Figure`
            Returns a handle to a figure with the 2 subplots.

        """
        fig = make_subplots(
            rows=2, cols=1,
            shared_xaxes=True,
            vertical_spacing=0.1,
            subplot_titles=("Beam schematic", "Reaction Forces")
        )

        fig = self.plot_beam_diagram(fig=fig, row=1, col=1)
        fig = self.plot_reaction_force(fig=fig, row=2, col=1)

        fig.update_xaxes(title_text='Beam Length (m)', row=2, col=1)

        fig.update_layout(
            height=550,
            width=700,
            title={'text': "Beam External Conditions", 'x': 0.5},
            title_font_size=24,
            showlegend=False,
            hovermode='x')

        return fig

    def plot_beam_internal(
            self,
            reverse_x=False,
            reverse_y=False):
        """A wrapper of several plotting functions that generates a
        single figure with 4 plots corresponding respectively to:

        - normal force diagram,
        - shear force diagram,
        - bending moment diagram, and
        - deflection diagram

        Parameters
        ----------
        reverse_x : bool, optional
            reverse the x axes, by default False
        reverse_y : bool, optional
            reverse the y axes, by default False

        Returns
        -------
        figure : `plotly.graph_objs._figure.Figure`
            Returns a handle to a figure with the 4 subplots.

        """
        fig = make_subplots(
            rows=4,
            cols=1,
            shared_xaxes=True,
            vertical_spacing=0.05,
            subplot_titles=(
                "Normal Force Diagram",
                "Shear Force Diagram",
                "Bending Moment Diagram",
                "Deflection Diagram"
            )
        )

        fig = self.plot_normal_force(
            reverse_x=reverse_x,
            reverse_y=reverse_y,
            fig=fig,
            row=1,
            col=1
        )
        fig = self.plot_shear_force(
            reverse_x=reverse_x,
            reverse_y=reverse_y,
            fig=fig,
            row=2,
            col=1
        )
        fig = self.plot_bending_moment(
            reverse_x=reverse_x,
            reverse_y=reverse_y,
            fig=fig,
            row=3,
            col=1
        )
        fig = self.plot_deflection(
            reverse_x=reverse_x,
            reverse_y=reverse_y,
            fig=fig,
            row=4,
            col=1
        )

        fig.update_xaxes(title_text='Beam Length (m)', row=4, col=1)

        fig.update_layout(
            height=1000,
            width = 700,
            title={'text': "Analysis Results", 'x': 0.5},
            title_font_size=24,
            showlegend=False,
        )

        return fig

    def plot_beam_diagram(self, fig=None, row=None, col=None):
        """Returns a schematic of the beam and all the loads applied on
        it

        Parameters
        ----------
        fig : bool, optional
            Figure to append subplot diagram too. If creating standalone
            figure then None, by default None
        row : int, optional
            row number if subplot, by default None
        col : int, optional
            column number if subplot, by default None

        Returns
        -------
        figure : `plotly.graph_objs._figure.Figure`
            Returns a handle to a figure with the beam schematic.
        """
        # can do point loads as arrows, not sure about directional point
        # loads though, hmm can have a set length for the arrow , say 50,
        # and use trigonometry to find the x and y offset to achieve.
        # for torques idk
        # hoverinfo is skip to not show any default values, hover
        # template is used to show only the x value and to not worry
        # about the y value
        data = go.Scatter(
            x=[self._x0, self._x1],
            y=[0, 0],
            mode='lines',
            name="Beam_",
            line=dict(color='purple', width=2),
            hovertemplate="%{x} m",
            hoverinfo='skip'
        )

        if fig and row and col:
            fig.add_trace(data, row=row, col=col)
            fig.update_yaxes(visible=False, range=[-3, 3], fixedrange=True,row=row,col=col)
        else:
            fig = go.Figure(data=data)
            # Hovermode x makes two hover labels appear if they are at
            # the same point (default setting means only see the last
            # updated point)
            fig.update_layout(
                title_text="Beam Schematic",
                title_font_size=24,
                showlegend=False,
                hovermode='x',
                title_x=0.5)
            fig.update_xaxes(title_text='Beam Length (m)')
            # visible false means y axis doesnt show, fixing range
            # means wont zoom in y direction

            fig.update_yaxes(visible=False, range=[-3, 3], fixedrange=True)

        # for each support append to figure to have the shapes/traces
        # needed for the drawing
        if row and col:
            for support in self._supports:
                fig = draw_support(fig, support, row=row, col=col)

            for load in self._loads:
                fig = draw_force(fig, load, row=row, col=col)
                fig = draw_load_hoverlabel(fig, load, row=row, col=col)
        else:
            for support in self._supports:
                fig = draw_support(fig, support)

            for load in self._loads:
                fig = draw_force(fig, load)
                fig = draw_load_hoverlabel(fig, load)

        return fig

    def plot_reaction_force(self, fig=None, row=None, col=None):
        """Returns a plot of the beam with reaction forces.

        Parameters
        ----------
        fig : bool, optional
            Figure to append subplot diagram too. If creating standalone
            figure then None, by default None
        row : int, optional
            row number if subplot, by default None
        col : int, optional
            column number if subplot, by default None

        Returns
        -------
        figure : `plotly.graph_objs._figure.Figure`
            Returns a handle to a figure with reaction forces.
        """
        # if a figure is passed it is for the subplot
        # append everything to it rather than creating a new plot.
        data = go.Scatter(
            x=[self._x0, self._x1],
            y=[0, 0],
            mode='lines',
            name="Beam",
            line=dict(color='purple', width=2),
            hovertemplate="%{x} m",
            hoverinfo='skip'
        )

        if fig and row and col:
            fig.add_trace(data, row=row, col=col)
            fig.update_yaxes(visible=False, range=[-3, 3], fixedrange=True,row=row,col=col)

        else:
            fig = go.Figure(data=data)

            # Hovermode x makes two hover labels appear if they are at
            # the same point (default setting means only see the last
            # updated point)
            fig.update_layout(
                title_text="Reaction Forces",
                title_font_size=24,
                showlegend=False,
                hovermode='x',
                title_x=0.5)

            fig.update_xaxes(title_text='Beam Length (m)')

        # visible false means y axis doesnt show, fixing range means
        # wont zoom in y direction
            fig.update_yaxes(visible=False, range=[-3, 3], fixedrange=True)

        for position, values in self._reactions.items():
            x_ = round(values[0], 3)
            y_ = round(values[1], 3)
            m_ = round(values[2], 3)

            #if there are reaction forces
            if abs(x_) > 0 or abs(y_)>0 or abs(m_) > 0:
                #subplot case
                if row and col:
                    fig = draw_reaction_hoverlabel(
                        fig,
                        reactions=[x_, y_, m_],
                        x_sup=position,
                        row=row,
                        col=col
                    )

                    if abs(x_) > 0:
                        fig = draw_force(
                            fig,
                            PointLoadH(x_, position),
                            row=row,
                            col=col
                        )
                    if abs(y_) > 0:
                        fig = draw_force(
                            fig,
                            PointLoadV(y_, position),
                            row=row,
                            col=col)
                    if abs(m_) > 0:
                        fig = draw_force(
                            fig,
                            PointTorque(m_, position),
                            row=row,
                            col=col
                        )
                else:
                    fig = draw_reaction_hoverlabel(
                        fig,
                        reactions=[x_, y_, m_],
                        x_sup=position
                    )

                    if abs(x_) > 0:
                        fig = draw_force(fig, PointLoadH(x_, position))
                    if abs(y_) > 0:
                        fig = draw_force(fig, PointLoadV(y_, position))
                    if abs(m_) > 0:
                        fig = draw_force(fig, PointTorque(m_, position))

        return fig

    def plot_normal_force(self, reverse_x=False, reverse_y=False, switch_axes=False,
                          fig=None, row=None, col=None):
        """Returns a plot of the normal force as a function of the
        x-coordinate.

        Parameters
        ----------
        reverse_x : bool, optional
            reverse the x axes, by default False
        reverse_y : bool, optional
            reverse the y axes, by default False
        switch_axes: bool, optional
            switch the x and y axis, by default False
        fig : bool, optional
            Figure to append subplot diagram too. If creating standalone
            figure then None, by default None
        row : int, optional
            row number if subplot, by default None
        col : int, optional
            column number if subplot, by default None

        Returns
        -------
        figure : `plotly.graph_objs._figure.Figure`
            Returns a handle to a figure with the normal force diagram.
        """

        xlabel = 'Beam Length'
        ylabel = 'Normal Force'
        xunits = 'm'
        yunits = 'kN'
        title = "Normal Force Plot"
        color = "red"

        fig = self.plot_analytical(
            self._normal_forces,
            color,
            title,
            xlabel,
            ylabel,
            xunits,
            yunits,
            reverse_x,
            reverse_y,
            switch_axes,
            fig=fig,
            row=row,
            col=col
        )
        return fig

    def plot_shear_force(self, reverse_x=False, reverse_y=False, switch_axes=False,
                        fig=None, row=None, col=None):
        """Returns a plot of the shear force as a function of the
        x-coordinate.

        Parameters
        ----------
        reverse_x : bool, optional
            reverse the x axes, by default False
        reverse_y : bool, optional
            reverse the y axes, by default False
        switch_axes: bool, optional
            switch the x and y axis, by default False
        fig : bool, optional
            Figure to append subplot diagram too. If creating standalone
            figure then None, by default None
        row : int, optional
            row number if subplot, by default None
        col : int, optional
            column number if subplot, by default None

        Returns
        -------
        figure : `plotly.graph_objs._figure.Figure`
            Returns a handle to a figure with the shear force diagram.
        """

        xlabel = 'Beam Length'
        ylabel = 'Shear Force'
        xunits = 'm'
        yunits = 'kN'
        title = "Shear Force Plot"
        color = "aqua"

        fig = self.plot_analytical(
            self._shear_forces,
            color,
            title,
            xlabel,
            ylabel,
            xunits,
            yunits,
            reverse_x,
            reverse_y,
            switch_axes,
            fig=fig,
            row=row,
            col=col
        )

        return fig

    def plot_bending_moment(self, reverse_x=False, reverse_y=False, switch_axes=False,
                        fig=None, row=None, col=None):
        """Returns a plot of the bending moment as a function of the
        x-coordinate.

        Parameters
        ----------
        reverse_x : bool, optional
            reverse the x axes, by default False
        reverse_y : bool, optional
            reverse the y axes, by default False
        switch_axes: bool, optional
            switch the x and y axis, by default False
        fig : bool, optional
            Figure to append subplot diagram too. If creating standalone
            figure then None, by default None
        row : int, optional
            row number if subplot, by default None
        col : int, optional
            column number if subplot, by default None

        Returns
        -------
        figure : `plotly.graph_objs._figure.Figure`
            Returns a handle to a figure with the bending moment diagram.
        """

        xlabel = 'Beam Length'
        ylabel = 'Bending Moment'
        xunits = 'm'
        yunits = 'kN.m'
        title = "Bending Moment Plot"
        color = "lightgreen"
        fig = self.plot_analytical(
            self._bending_moments,
            color,
            title,
            xlabel,
            ylabel,
            xunits,
            yunits,
            reverse_x,
            reverse_y,
            switch_axes,
            fig=fig,
            row=row,
            col=col)

        return fig

    def plot_deflection(self, reverse_x=False, reverse_y=False, switch_axes=False,
                        fig=None, row=None, col=None):
        """Returns a plot of the beam deflection as a function of the
        x-coordinate.

        Parameters
        ----------
        reverse_x : bool, optional
            reverse the x axes, by default False
        reverse_y : bool, optional
            reverse the y axes, by default False
        switch_axes: bool, optional
            switch the x and y axis, by default False
        fig : bool, optional
            Figure to append subplot diagram too. If creating standalone
            figure then None, by default None
        row : int, optional
            row number if subplot, by default None
        col : int, optional
            column number if subplot, by default None

        Returns
        -------
        figure : `plotly.graph_objs._figure.Figure`
            Returns a handle to a figure with the deflection diagram.
        """

        xlabel = 'Beam Length'
        ylabel = 'Deflection'
        xunits = 'm'
        yunits = 'mm'
        title = "Deflection Plot"
        color = "blue"
        fig = self.plot_analytical(
            self._deflection_equation,
            color,
            title,
            xlabel,
            ylabel,
            xunits,
            yunits,
            reverse_x,
            reverse_y,
            switch_axes,
            fig=fig,
            row=row,
            col=col
        )

        return fig

    def plot_axial_deflection(self, reverse_x=False, reverse_y=False, switch_axes=False,
                              fig=None, row=None, col=None):
        """Returns a plot of the beam axial deflection as a function 
        of the x-coordinate.

        Parameters
        ----------
        reverse_x : bool, optional
            reverse the x axes, by default False
        reverse_y : bool, optional
            reverse the y axes, by default False
        switch_axes: bool, optional
            switch the x and y axis, by default False
        fig : bool, optional
            Figure to append subplot diagram too. If creating standalone
            figure then None, by default None
        row : int, optional
            row number if subplot, by default None
        col : int, optional
            column number if subplot, by default None

        Returns
        -------
        figure : `plotly.graph_objs._figure.Figure`
            Returns a handle to a figure with the axial deflection diagram.
        """

        xlabel = 'Beam Length'
        ylabel = 'Axial Deflection'
        xunits = 'm'
        yunits = 'mm'
        title = "Axial Deflection Plot"
        color = "blue"
        fig = self.plot_analytical(
            self._axial_deflection,
            color,
            title,
            xlabel,
            ylabel,
            xunits,
            yunits,
            reverse_x,
            reverse_y,
            switch_axes,
            fig=fig,
            row=row,
            col=col
        )

        return fig

    def plot_analytical(self, sym_func, color="blue", title="", xlabel="",
                        ylabel="", xunits="", yunits="", reverse_x=False,
                        reverse_y=False, switch_axes = False, fig=None, row=None, col=None):
        """
        Auxiliary function for plotting a sympy.Piecewise analytical
        function.

        Parameters
        -----------
        sym_func: sympy function
            symbolic function using the variable x
        color: str
            color to be used for plot, default blue.
        title: str
            title to show above the plot, optional
        xlabel: str
            physical variable displayed on the x-axis. Example: "Length"
        ylabel: str
            physical variable displayed on the y-axis. Example: "Shear
            force"
        xunits: str
            physical unit to be used for the x-axis. Example: "m"
        yunits: str
            phsysical unit to be used for the y-axis. Example: "kN"
        reverse_x : bool, optional
            reverse the x axes, by default False
        reverse_y : bool, optional
            reverse the y axes, by default False
        switch_axes: bool, optional
            switch the x and y axis, by default False
        fig : bool, optional
            Figure to append subplot diagram too. If creating standalone
            figure then None, by default None
        row : int, optional
            row number if subplot, by default None
        col : int, optional
            column number if subplot, by default None


        Returns
        -------
        figure : `plotly.graph_objs._figure.Figure`
            Returns a handle to a figure with the deflection diagram.
        """
        # numpy array for x positions closely spaced (allow for graphing)
        x_vec = np.linspace(self._x0, self._x1, int(1000))
        # transform sympy expressions to lambda functions which can be used to
        # calculate numerical values very fast (with numpy)
        y_lam = lambdify(x, sym_func, "numpy")
        y_vec = np.array([y_lam(t) for t in x_vec])
        # np.array for y values created
        # np.array for y values created
        fill = 'tozeroy'

        if switch_axes:
            x_vec, y_vec = y_vec, x_vec
            xlabel, ylabel = ylabel, xlabel
            xunits, yunits = yunits, xunits
            fill = 'tozerox'

            # will also need to update the annotation furtehr down
            # can also try add units to hoverlabels using meta?



        data = go.Scatter(
            x=x_vec.tolist(),
            y=y_vec.tolist(),
            mode='lines',
            line=dict(color=color, width=1),
            fill=fill,
            name=ylabel,
            hovertemplate="%{x:.3f} <br>%{y:.3f} "
        )

        if row and col and fig:
            fig = fig.add_trace(data, row=row, col=col)
        else:
            fig = go.Figure(data=data)
            fig.update_layout(title_text=title, title_font_size=30)
            fig.update_xaxes(title_text=str(xlabel + " (" + str(xunits) + ")"))

        if row and col:
            fig.update_yaxes(
                title_text=str(ylabel + " (" + str(yunits) + ")"),
                row=row,
                col=col
            )
            fig.update_yaxes(
                autorange="reversed", row=row, col=col
            ) if reverse_y else None
            fig.update_xaxes(
                autorange="reversed", row=row, col=col
            ) if reverse_x else None
        else:
            fig.update_yaxes(title_text=str(ylabel + " (" + str(yunits) + ")"))
            fig.update_yaxes(autorange="reversed") if reverse_y else None
            fig.update_xaxes(autorange="reversed") if reverse_x else None

        for q_val in self._query:
            q_res = self._get_query_value(q_val, sym_func)
            if q_res < 0:
                ay = 40
            else:
                ay = -40

            if switch_axes:

                annotation = dict(
                    x=q_res, y=q_val,
                    text=f"{str(q_val)}<br>{str(q_res)}",
                    showarrow=True,
                    arrowhead=1,
                    xref='x',
                    yref='y',
                    ax=ay,
                    ay=0,
                )
            else:
                annotation = dict(
                    x=q_val, y=q_res,
                    text=f"{str(q_val)}<br>{str(q_res)}",
                    showarrow=True,
                    arrowhead=1,
                    xref='x',
                    yref='y',
                    ax=0,
                    ay=ay
                )
            if row and col:
                fig.add_annotation(annotation, row=row, col=col)
            else:
                fig.add_annotation(annotation)

        return fig

    def _update_distributed_loads(self, load, remove = False):
        # Load object should only ever be a DistributedLoad/H/V object.
        # If remove is true will aim to remove it if it is there
        # otherwise add it in only if it is not already there.
        # (if it is already there then the result would be the smame and 
        # would be inefficient to do the whole thing again)

        # if distributed load v
        if isinstance(load, DistributedLoadV):
            # if remove = False and the load isnt a key then
            # set the load as a key and associate with the integrals needed
            # be calling _create_distributed_force
            if not remove and load not in self._distributed_forces_y.keys():
                self._distributed_forces_y[load] = self._create_distributed_force(load)
            elif remove and load in self._distributed_forces_y.keys():
                self._distributed_forces_y.pop(load)

        elif isinstance(load, DistributedLoadH):
            if not remove and load not in self._distributed_forces_x.keys():
                self._distributed_forces_x[load] = self._create_distributed_force(load)
            elif remove and load in self._distributed_forces_x.keys():
                self._distributed_forces_x.pop(load)
        
        elif isinstance(load, DistributedLoad):
            force, position, angle = load
            force = sympify(force)

            force_x = force * cos(radians(angle)).evalf(6)
            force_y = force * sin(radians(angle)).evalf(6)

            if abs(round(force_y.subs(x,1), 5)) > 0 or abs(round(force_y.subs(x,0), 5)) > 0:   # This expression is bad cause the value could just be 0 at a point
                a = DistributedLoadV(force_y, position)
                if not remove and load not in self._distributed_forces_y.keys():
                    self._distributed_forces_y[a] = self._create_distributed_force(a)
                elif remove and load in self._distributed_forces_y.keys():
                    self._distributed_forces_y.pop(a)

            if abs(round(force_x.subs(x,1), 5)) > 0 or abs(round(force_x.subs(x,0), 5)) > 0:
                b = DistributedLoadH(force_x, position)
                if not remove and load not in self._distributed_forces_x.keys():
                    self._distributed_forces_x[b] = self._create_distributed_force(b)
                elif remove and load in self._distributed_forces_x.keys():
                    self._distributed_forces_x.pop(b)

    def _create_distributed_force(
            self,
            load: DistributedLoadH or DistributedLoadV):
        """
        Create a sympy.Piecewise object representing the provided 
        distributed load.

        :param expr: string with a valid sympy expression.
        :param interval: tuple (x0, x1) containing the extremes of the 
        interval on which the load is applied.
        :param shift: when set to False, the x-coordinate in the 
        expression is referred to the left end of the beam, instead 
        of the left end of the provided interval.
        :return: sympy.Piecewise object with the value of the 
        distributed load.
        """
        expr, interval = load
        x0, x1 = interval
        expr = sympify(expr)

        # a list to contain an expression for a distributed laod and
        # the values of the expression at either end

        t1 = time.perf_counter()

        func_list = [[expr, 0]]
        for a in range(1,5):
            # integrate main function and solve to equal 0 at left
            func = integrate(func_list[-1][0], x)
            c1 = func.subs(x, x0)
            func -= c1

            # integrate second function
            func_2 = integrate(func_list[-1][1], x)
            c2 = func.subs(x, x1)
            func_2 += c2 - func_2.subs(x, x1) 

            func_list.append([func, func_2])


        a = Piecewise((0, x < x0), (0, x > x1), (func_list[0][0], True))
        b = Piecewise((0, x < x0), (func_list[1][0], x <= x1), (func_list[1][1], True))
        c = Piecewise((0, x < x0), (func_list[2][0], x <= x1), (func_list[2][1], True))
        d = Piecewise((0, x < x0), (func_list[3][0], x <= x1), (func_list[3][1], True))
        e = Piecewise((0, x < x0), (func_list[4][0], x <= x1), (func_list[4][1], True))
        f = func_list[1][1]
        print(t1 - time.perf_counter())
        if isinstance(load, DistributedLoadV):
            return (
                a,
                b,
                c,
                d,
                e,
                f,
                integrate(expr * x, (x, x0, x1)),
            )

        elif isinstance(load, DistributedLoadH):
            return (
                a,
                b,
                c,
                0,
                0,
                f,
                0,
            )
                
    def _effort_from_pointload(
            self, load: PointLoadH or PointLoadV or PointTorque):
        """
        Create a sympy.Piecewise object representing the shear force 
        caused by a point load.

        :param value: float or string with the numerical value of the 
        point load.
        :param coord: x-coordinate on which the point load is applied.
        :return: sympy.Piecewise object with the value of the shear 
        force produced by the provided point load.
        """
        value, coord = load
        return Piecewise((0, x < coord), (value, True))

    # def _point_loads_x(self):
    #     for f in self._loads:
    #         if isinstance(f, PointLoadH):
    #             yield f
    #         elif isinstance(f, PointLoad):
    #             force, position, angle = f
    #             # when angle = 0 then force is 1
    #             force_x = sympify(force * cos(radians(angle))).evalf(10)

    #             if abs(round(force_x, 3)) > 0:
    #                 yield PointLoadH(force_x, position)

    # def _point_loads_y(self):
    #     for f in self._loads:
    #         if isinstance(f, PointLoadV):
    #             yield f
    #         elif isinstance(f, PointLoad):
    #             force, position, angle = f
    #             # when angle = 90 then force is 1
    #             force_y = sympify(force * sin(radians(angle))).evalf(10)

    #             if abs(round(force_y, 3)) > 0:
    #                 yield PointLoadV(force_y, position)

    # def _distributed_loads_x(self):
    #     for f in self._loads:
    #         if isinstance(f, DistributedLoadH):
    #             yield f
    #         elif isinstance(f, DistributedLoad):
    #             force, position, angle = f

    #             force = sympify(force)
    #             force_x = force * cos(radians(angle)).evalf(10)
    #             if abs(round(force_x.subs(x,1), 5)) > 0:
    #                 yield DistributedLoadH(force_x, position)

    # def _distributed_loads_y(self):
    #     for f in self._loads:
    #         if isinstance(f, DistributedLoadV):
    #             yield f
    #         elif isinstance(f, DistributedLoad):
    #             force, position, angle = f

    #             force = sympify(force)
    #             force_y = force * sin(radians(angle)).evalf(10)
    #             if abs(round(force_y.subs(x,1), 5)) > 0:
    #                 yield DistributedLoadV(force_y, position)

    # def _point_torques(self):
    #     for f in self._loads:
    #         if isinstance(f, PointTorque):
    #             yield f

    def __str__(self):
        return f"""--------------------------------
        <Beam>
        length = {self._x0}
        loads = {str(len(self._loads))}"""

    def __repr__(self):
        return f"<Beam({self._x0})>"

    def __add__(self, other):
        new_beam = deepcopy(self)
        # add loads in beam other to new beam.
        # new_beam.add_loads(other._loads) 


if __name__ == "__main__":
    t1 = time.perf_counter()
    beam = Beam(7)                          # Initialize a Beam object of length 9m with E and I as defaults
    beam_2 = Beam(9,E=2000, I =100000)      # Initializa a Beam specifying some beam parameters

    a = Support(5,(1,1,0))                  # Defines a pin support at location x = 5m  
    b = Support(0,(0,1,0))                  # Defines a roller support at location x = 0m
    c = Support(7,(1,1,1))                  # Defines a fixed support at location x = 7m
    beam.add_supports(a,b,c)    

    load_1 = PointLoadV(1,2)                # Defines a point load of 1kn acting up, at location x = 2m   # Defines a 2kN UDL from location x = 1m to x = 4m 
    load_3 = PointTorque(2, 3.5)              # Defines a 2kN.m point torque at location x = 3.5m
    load_2 = TrapezoidalLoad((0,5),(0,5),90)
    load_4 = TrapezoidalLoad((5,5),(1,4),90)
    load_5 = DistributedLoad("2 * x + 5",(0,5),90)

    load_6 = TrapezoidalLoad((1,2),(1,2),45)
    load_7 = TrapezoidalLoadV((2,2),(2,3))
    load_8 = TrapezoidalLoadH((2,3),(2,3))
    load_9 = DistributedLoad("2 * x + 5",(0,5),45)
    load_10 = DistributedLoadV("2 * x * x + 5",(0,5))
    load_11 = DistributedLoadH("2 * x + 5",(0,5))
    
    beam.add_loads(load_1,load_3, load_2, load_4, load_5,load_6, load_7, load_8, load_9, load_10, load_11)           # Assign the support objects to a beam object created earlier

    beam.analyse()