import numpy

from amuse.support.exceptions import AmuseException
from amuse.datamodel import Particles
from amuse.units import units, quantities, constants

from amuse.ext.evrard_test import uniform_unit_sphere


def kudritzki_wind_velocity(mass, radius, luminosity, temperature,
                            Y=0.25, I_He=2):
    """
      This routine calculates the escape and terminal wind velocity. The
      Equations are taken from Kudritzki & Puls, Annual Reviews of Astronomy
      and Astrophysics, 2000, Vol. 38, p.613-666 Equation (8) and (9) and
      Kudritzki et al., 1989, A&A 219, 205 Equation (64) and (65).

      I_He:    Number of electrons per He nucleus (= 2 in O-Stars)
      sigma_e:   Thomson absorption coefficient
      Gamma:     Ratio of radiative Thomson to gravitational acceleration
    """
    sigma_e = 0.398 * (1 + I_He*Y)/(1 + 4*Y)
    Gamma = 7.66E-5 * sigma_e * (luminosity.value_in(units.LSun)
                                 / mass.value_in(units.MSun))
    v_esc = (2*constants.G * mass / radius*(1 - Gamma))**0.5

    condlist = [temperature >= 21000. | units.K,
                (10000. | units.K < temperature) &
                (temperature < 21000. | units.K),
                temperature <= 10000. | units.K]
    choicelist = [2.65, 1.4, 1.0]

    return v_esc * numpy.select(condlist, choicelist)


class PositionGenerator(object):
    def __init__(self, grid_type="random"):
        self.cube_generator = {
            "random": self.random_cube,
            "regular": self.regular_grid_unit_cube,
            "body_centered": self.body_centered_grid_unit_cube,
            }[grid_type]

    def as_three_vector(self, array):
        number = array
        if quantities.is_quantity(array):
            number = array.number
        three_vector = numpy.transpose([number]*3)
        if quantities.is_quantity(array):
            three_vector = three_vector | array.unit
        return three_vector

    def regular_grid_unit_cube(self):
        self.targetN=targetN
        self.par=long(float(targetN)**(1./3.)+1.5)
        nf=self.par
        dnf=1./(nf)
        x,y,z=numpy.mgrid[-1.+dnf:1.-dnf:nf*1j,-1.+dnf:1.-dnf:nf*1j,-1.+dnf:1.-dnf:nf*1j]
        x=x.flatten()
        y=y.flatten()
        z=z.flatten()
        return x,y,z

    def body_centered_grid_unit_cube(self):
        self.targetN=targetN
        self.par=long(float(targetN/2.)**(1./3.)+1.5)
        nf=self.par
        x1,y1,z1=numpy.mgrid[-1.:1.:nf*1j,
                             -1.:1.:nf*1j,
                             -1.:1.:nf*1j]
        x2,y2,z2=numpy.mgrid[-1.+1./nf:1.-1./nf:(nf-1)*1j,
                             -1.+1./nf:1.-1./nf:(nf-1)*1j,
                             -1.+1./nf:1.-1./nf:(nf-1)*1j]
        x=numpy.concatenate( (x1.flatten(),x2.flatten()) )
        y=numpy.concatenate( (y1.flatten(),y2.flatten()) )
        z=numpy.concatenate( (z1.flatten(),z2.flatten()) )
        a=numpy.where((x>=-1) & (y>=-1) & (z>=-1) & (x<1) & (y<1) & (z<1) )[0]
        return x[a],y[a],z[a]

    def random_cube(self, N):
        numbers = numpy.random.uniform(-1., 1., 3 * N)
        return numpy.reshape(numbers, (N, 3))

    def cutout_sphere(self, positions, rmin):
        r = numpy.sqrt((positions**2).sum(1))
        return positions[(r >= rmin) & (r < 1)]

    def uniform_hollow_sphere(self, N, rmin):
        cube_sphere_ratio = 4/3. * numpy.pi * 0.5**3 * (1 - rmin**3)
        estimatedN = N / cube_sphere_ratio

        while True:
            estimatedN = estimatedN * 1.1 + 1
            cube = self.cube_generator(int(estimatedN))
            hollow_sphere = self.cutout_sphere(cube, rmin)
            if len(hollow_sphere) >= N:
                break

        return hollow_sphere[:N]

    def generate_positions(self, N, rmin, rmax, radius_function=None, star=None):
        """
            The particles start out in a (random) position between
            the surface of the star and the distance that the
            previously released particles have reached.
            This assumes that the current wind velocity is
            comparable to the previous wind velocity.

            Note that the stellar position is not added yet here.
        """
        positions = self.uniform_hollow_sphere(N, 1. * rmin / rmax)
        vector_lengths = numpy.sqrt((positions**2).sum(1))

        unit_vectors = positions/self.as_three_vector(vector_lengths)

        int_v_over_total = ((vector_lengths * rmax)**3 - rmin**3) / (rmax**3 - rmin**3)

        if radius_function is not None:
            distance = radius_function(int_v_over_total, rmax, star)
        else:

            distance = int_v_over_total * (rmax - rmin) + rmin
        position = unit_vectors * self.as_three_vector(distance)

        return position, unit_vectors


class StarsWithMassLoss(Particles):
    def __init__(self, *args, **kwargs):
        super(StarsWithMassLoss, self).__init__(*args, **kwargs)
        self.collection_attributes.timestamp = 0. | units.yr
        self.collection_attributes.previous_time = 0. | units.yr
        self.collection_attributes.track_mechanical_energy = False

    def add_particles(self, particles, *args, **kwargs):
        new_particles = super(StarsWithMassLoss, self).add_particles(
            particles, *args, **kwargs)

        """
            TODO: there is a better way to define defaults
            override:
                can_extend_attributes
                set_value_in_store
                get_attribute_names_defined_in_store
                look at ParticlesWithFilteredAttributes as an example

        """

        attributes = particles.get_attribute_names_defined_in_store()
        if 'lost_mass' not in attributes:
            new_particles.lost_mass = 0. | units.MSun
        if 'wind_release_time' not in attributes:
            new_particles.wind_release_time = (self.collection_attributes.
                                               timestamp)
        if 'mu' not in attributes:
            new_particles.mu = self.collection_attributes.global_mu

        if self.collection_attributes.track_mechanical_energy:
            if 'mechanical_energy' not in attributes:
                new_particles.mechanical_energy = quantities.zero
            if 'previous_mechanical_luminosity' not in attributes:
                new_particles.previous_mechanical_luminosity = -1 | units.W
                self.collection_attributes.new_unset_lmech_particles = True

        return new_particles

    def evolve_mass_loss(self, time):
        if self.collection_attributes.previous_time > time:
            # TODO: do we really need this check? Why?
            return

        elapsed_time = time - self.collection_attributes.previous_time
        self.lost_mass += elapsed_time * self.wind_mass_loss_rate

        if self.collection_attributes.track_mechanical_energy:
            new_mechanical_luminosity = (0.5 * self.wind_mass_loss_rate
                                         * self.terminal_wind_velocity**2)

            if self.collection_attributes.new_unset_lmech_particles:
                i_new = self.previous_mechanical_luminosity < quantities.zero
                self[i_new].previous_mechanical_luminosity =\
                    new_mechanical_luminosity[i_new]
                self.collection_attributes.new_unset_lmech_particles = False

            average_mechanical_luminosity = 0.5 * (
                self.previous_mechanical_luminosity
                + new_mechanical_luminosity)
            self.mechanical_energy += (elapsed_time
                                       * average_mechanical_luminosity)

            self.previous_mechanical_luminosity = new_mechanical_luminosity

        self.collection_attributes.timestamp = time
        self.collection_attributes.previous_time = time

    def track_mechanical_energy(self, track):
        self.collection_attributes.track_mechanical_energy = track

    def set_global_mu(self, mu):
        self.mu = mu
        self.collection_attributes.global_mu = mu

    def reset(self):
        self.lost_mass = 0.0 | units.MSun
        self.set_begin_time(0. | units.yr)

    def set_begin_time(self, time):
        self.wind_release_time = time
        self.collection_attributes.timestamp = time
        self.collection_attributes.previous_time = time


class EvolvingStarsWithMassLoss(StarsWithMassLoss):
    """
        Derive the stellar wind from stellar evolution.
        You have to copy the relevant attributes from the stellar evolution.
        This can be done using a channel like:

        chan = stellar_evolution.particles.new_channel_to(
            stellar_wind.particles,
            attributes=["age", "radius", "mass", "luminosity", "temperature"])

        while <every timestep>:
            chan.copy()
    """

    def add_particles(self, particles, *args, **kwargs):
        new_particles = super(EvolvingStarsWithMassLoss, self).add_particles(
            particles, *args, **kwargs)
        attributes = particles.get_attribute_names_defined_in_store()
        if 'wind_mass_loss_rate' not in attributes:
            new_particles.wind_mass_loss_rate = 0. | units.MSun/units.yr
        if 'previous_age' not in attributes:
            new_particles.previous_age = new_particles.age
        if 'previous_mass' not in attributes:
            new_particles.previous_mass = new_particles.mass
        return new_particles

    def evolve_mass_loss(self, time):
        if self.collection_attributes.previous_time <= time:
            self.update_from_evolution()
            StarsWithMassLoss.evolve_mass_loss(self, time)

    def update_from_evolution(self):
        if (self.age != self.previous_age).any():
            mass_loss = self.previous_mass - self.mass
            timestep = self.age - self.previous_age
            self.wind_mass_loss_rate = mass_loss / timestep

            self.previous_age = self.age
            self.previous_mass = self.mass


class SimpleWind(PositionGenerator):
    """
        The simple wind model creates SPH particles moving away
        from the star at the terminal velocity.
        This is a safe assumption if the distance to other objects
        is (far) larger then the stellar radius.
    """

    def __init__(self, sph_particle_mass, derive_from_evolution=False,
                 tag_gas_source=False, compensate_gravity=False, **kwargs):
        super(SimpleWind, self).__init__(**kwargs)
        self.sph_particle_mass = sph_particle_mass
        self.model_time = 0.0 | units.yr

        if derive_from_evolution:
            self.particles = EvolvingStarsWithMassLoss()
            self.particles.add_calculated_attribute(
                "terminal_wind_velocity", kudritzki_wind_velocity,
                attributes_names=['mass', 'radius',
                                  'luminosity', 'temperature'])
        else:
            self.particles = StarsWithMassLoss()

        self.target_gas = self.timestep = None
        self.tag_gas_source = tag_gas_source
        self.compensate_gravity = compensate_gravity

        self.set_global_mu()
        self.internal_energy_formula = self.internal_energy_from_temperature
        self.set_initial_wind_velocity()

    def set_initial_wind_velocity(self):
        self.particles.add_calculated_attribute(
            "initial_wind_velocity", lambda v: v,
            attributes_names=['terminal_wind_velocity'])

    def evolve_particles(self):
        self.particles.evolve_mass_loss(self.model_time)

    def evolve_model(self, time):
        if self.has_target():
            while self.model_time <= time:
                self.evolve_particles()
                if self.has_new_wind_particles():
                    wind_gas = self.create_wind_particles()
                    self.target_gas.add_particles(wind_gas)
                self.model_time += self.timestep
        else:
            self.model_time = time
            self.evolve_particles()

    def set_target_gas(self, target_gas, timestep):
        self.target_gas = target_gas
        self.timestep = timestep

    def has_target(self):
        return self.target_gas is not None

    def set_global_mu(self, Y=0.25, Z=0.02, x_ion=0.1):
        """
            Set the global value of mu used to create stellar wind.
            If the value of mu is known directly,
            use <stellar_wind>.particles.set_global_mu().
            An alternative way is to set mu for each star separately.
        """
        X = 1.0 - Y - Z
        mu = constants.proton_mass / (X*(1.0+x_ion) + Y*(1.0+2.0*x_ion)/4.0
                                      + Z*x_ion/2.0)
        self.particles.set_global_mu(mu)

    def internal_energy_from_temperature(self, star, wind=None):
        """
            set the internal energy from the stellar surface temperature.
        """
        return (3./2. * constants.kB * star.temperature / star.mu)

    def internal_energy_from_velocity(self, star, wind=None):
        """
            set the internal energy from the terminal wind velocity.
        """

        return 0.5 * star.terminal_wind_velocity**2

    def wind_sphere(self, star, Ngas):
        wind = Particles(Ngas)

        wind_velocity = star.initial_wind_velocity

        outer_wind_distance = star.radius + wind_velocity * (
            self.model_time - star.wind_release_time)

        wind.position, direction = self.generate_positions(
            Ngas, star.radius, outer_wind_distance)

        if self.compensate_gravity:
            r = wind.position.lengths()
            escape_velocity_squared = 2. * constants.G * star.mass / r
            speed = (wind_velocity**2 + escape_velocity_squared).sqrt()
            wind.velocity = self.as_three_vector(speed) * direction
        else:
            wind.velocity = direction * wind_velocity

        return wind

    def create_wind_particles_for_one_star(self, star):
        Ngas = int(star.lost_mass/self.sph_particle_mass)
        star.lost_mass -= Ngas * self.sph_particle_mass

        wind = self.wind_sphere(star, Ngas)

        wind.mass = self.sph_particle_mass
        wind.u = self.internal_energy_formula(star, wind)
        wind.position += star.position
        wind.velocity += star.velocity

        if self.tag_gas_source:
            wind.source = star.key

        return wind

    def create_wind_particles(self):
        wind = Particles(0)

        for star in self.particles:
            if star.lost_mass > self.sph_particle_mass:
                new_particles = self.create_wind_particles_for_one_star(star)
                wind.add_particles(new_particles)
                star.wind_release_time = self.model_time

        return wind

    def has_new_wind_particles(self):
        return self.particles.lost_mass.max() > self.sph_particle_mass

    def create_initial_wind(self, number=None, time=None, check_length=True):
        """
            This is a convenience method that creates some initial particles.
            They are created as if the wind has already been blowing for
            'time'.  Note that this does not work if the mass loss is derived
            from stellar evolution.

            If 'number' is given, the required time to get that number of
            particles is calculated. This assumes that the number of expected
            particles is far larger then the number of stars
        """
        if number is not None:
            required_mass = number * self.sph_particle_mass
            total_mass_loss = self.particles.wind_mass_loss_rate.sum()
            time = 1.0 * required_mass/total_mass_loss
        self.model_time = time
        self.particles.evolve_mass_loss(self.model_time)

        if self.has_new_wind_particles():
            wind_gas = self.create_wind_particles()
            if self.has_target():
                self.target_gas.add_particles(wind_gas)
        elif check_length:
            raise AmuseException("create_initial_wind time was too small to"
                                 "create any particles.")
        else:
            wind_gas = Particles()

        self.reset()

        return wind_gas

    def reset(self):
        self.particles.reset()
        self.model_time = 0.0 | units.yr

    def set_begin_time(self, time):
        self.model_time = time
        self.particles.set_begin_time(time)

    def get_gravity_at_point(self, eps, x, y, z):
        return [0, 0, 0] | units.m/units.s**2

    def get_potential_at_point(self, radius, x, y, z):
        return [0, 0, 0] | units.J


class AccelerationFunction(object):
    """
    Abstact superclass of all acceleration functions.
    It numerically derives everything from using acceleration_from_radius
    Overwrite as many of these functions with analitic solutions as possible.
    """

    def __init__(self):
        try:
            from scipy import integrate, optimize
            self.quad = integrate.quad
            # self.root = optimize.root
            self.brentq = optimize.brentq
        except ImportError:
            self.quad = self.unsupported
            # self.root = self.unsupported
            self.brentq = self.unsupported

    def unsupported(self, *args, **kwargs):
        raise AmuseException("Importing SciPy has failed")

    def acceleration_from_radius(self, radius, star):
        """
            to be overridden
        """
        pass

    def velocity_from_radius(self, radius, star):

        def stripped_acceleration(r1):
            acc = self.acceleration_from_radius(r1 | units.RSun, star)
            return acc.value_in(units.RSun/units.yr**2)

        def acc_integral(r):
            start = star.radius.value_in(units.RSun)

            result = self.quad(stripped_acceleration, start, r)
            return result[0]

        integral = numpy.vectorize(acc_integral)(radius.value_in(units.RSun))
        integral = integral | units.RSun**2/units.yr**2

        return (2. * integral + star.initial_wind_velocity**2).sqrt()

    def radius_from_time(self, time, star):
        """
            following http://math.stackexchange.com/questions/54586/
            converting-a-function-for-velocity-vs-position-vx-to-position-vs-time
        """

        def inverse_velocity(r1):
            velocity = self.velocity_from_radius(r1 | units.RSun, star)
            return 1. / velocity.value_in(units.RSun/units.yr)

        def one_radius(t):
            def residual(r2):
                start = star.radius.value_in(units.RSun)
                result = self.quad(inverse_velocity, start, r2)
                return result[0] - t.value_in(units.yr)

            start = star.radius.value_in(units.RSun)
            end = 1e5 * start
            result = self.brentq(residual, start, end)

            return result

        radius = numpy.vectorize(one_radius)(time)
        return radius | units.RSun

    def radius_from_number(self, numbers, max_radius, star):
        """
            See http://www.av8n.com/physics/arbitrary-probability.htm
            for some good info on this.
        """

        rmin = star.radius.value_in(units.RSun)
        rmax = max_radius.value_in(units.RSun)

        def inverse_velocity(r1):
            velocity = self.velocity_from_radius(r1 | units.RSun, star)
            velocity = velocity.value_in(units.RSun/units.s)
            return 1. / velocity

        def cumulative_inverse_velocity(q):
            res = self.quad(inverse_velocity, rmin, q)
            return res[0]

        d_max = cumulative_inverse_velocity(rmax)

        def one_radius(x):
            def residual(r2):
                return cumulative_inverse_velocity(r2) / d_max - x

            return self.brentq(residual, rmin, rmax)

        radius = numpy.vectorize(one_radius)(numbers)

        return radius | units.RSun

    def fix_cutoffs(self, test, value, star, default):
        if hasattr(value, "__len__"):
            value[test] = default
        elif test:
            value = default
        return value

    def fix_acc_cutoff(self, r, acc, star):
        test = r > star.acc_cutoff
        return self.fix_cutoffs(test, acc, star, quantities.zero)

    def fix_v_cutoff(self, r, v, star):
        test = r > star.acc_cutoff
        return self.fix_cutoffs(test, v, star, star.terminal_wind_velocity)


class ConstantVelocityAcceleration(AccelerationFunction):
    """
        A very basic "acceleration" function that ensures a constant velocity,
    """

    def acceleration_from_radius(self, radius, star):
        return numpy.zeros_like(radius, dtype=float) | units.m/units.s**2

    def velocity_from_radius(self, radius, star):
        velocity = star.terminal_wind_velocity
        return numpy.ones_like(radius, dtype=float) * velocity

    def radius_from_time(self, t, star):
        return star.radius + t * star.terminal_wind_velocity

    def radius_from_number(self, x, r_max, star):
        r_star = star.radius
        return x * (r_max - r_star) + r_star


class RSquaredAcceleration(AccelerationFunction):
    def scaling(self, star):
        return 0.5 * ((star.terminal_wind_velocity**2
                       - star.initial_wind_velocity**2)
                      / (1./star.radius - 1./star.acc_cutoff))

    def acceleration_from_radius(self, r, star):
        acc = self.scaling(star)/r**2
        return self.fix_acc_cutoff(r, acc, star)

    def velocity_from_radius(self, r, star):
        v = (2 * self.scaling(star) * (1./star.radius - 1./r)
             + star.initial_wind_velocity**2).sqrt()
        return self.fix_v_cutoff(r, v, star)


class DelayedRSquaredAcceleration(AccelerationFunction):
    def scaling(self, star):
        return 0.5 * ((star.terminal_wind_velocity**2
                       - star.initial_wind_velocity**2)
                      / (1./star.acc_start - 1./star.acc_cutoff))

    def fix_acc_start_cutoff(self, r, acc, star):
        return self.fix_cutoffs(r < star.acc_start, acc, star, quantities.zero)

    def fix_v_start_cutoff(self, r, v, star):
        test = r < star.acc_start
        return self.fix_cutoffs(test, v, star, star.initial_wind_velocity)

    def acceleration_from_radius(self, r, star):
        acc = self.scaling(star)/r**2
        acc = self.fix_acc_start_cutoff(r, acc, star)
        return self.fix_acc_cutoff(r, acc, star)

    def velocity_from_radius(self, r, star):
        v = (2 * self.scaling(star) * (1./star.acc_start - 1./r)
             + star.initial_wind_velocity**2).sqrt()
        v = self.fix_v_start_cutoff(r, v, star)
        return self.fix_v_cutoff(r, v, star)


class NowotnyAcceleration(AccelerationFunction):
    def acceleration_from_radius(self, r, star):
        """ To be included by Martha """
        pass

    def velocity_from_radius(self, r, star):
        """ To be included by Martha """
        pass


class VelocityLawAcceleration(AccelerationFunction):
    """ Following Walter Maciel 2005 """

    def __init__(self, alpha=4):
        self.alpha = alpha

    def acceleration_from_radius(self, r, star):
        v_start = star.initial_wind_velocity
        v_end = star.terminal_wind_velocity
        dvdr = (2 * star.radius * (1 - star.radius / r)
                * (v_end - v_start) / r**2)
        return dvdr * self.velocity_from_radius(self, r, star)

    def velocity_from_radius(self, r, star):
        v_start = star.initial_wind_velocity
        v_end = star.terminal_wind_velocity
        return v_start + (v_end - v_start) * (1 - star.radius/r)**self.alpha


class LogisticVelocityAcceleration(AccelerationFunction):
    """ The velocity follows the Logistic (Sigmoid) Function """

    def __init__(self, steepness=10, r_mid=None):
        super(LogisticVelocityAcceleration, self).__init__()
        self.steepness = steepness
        self.r_mid = r_mid

    def short(self, r, star):
        v_init = star.initial_wind_velocity
        v_end = star.terminal_wind_velocity

        if self.r_mid is None:
            r_mid = (star.acc_cutoff + star.radius)/2.
        else:
            r_mid = self.r_mid * star.radius
        exp = numpy.exp(-self.steepness * (r - r_mid) / (r_mid))

        return v_init, v_end, r_mid, exp

    def acceleration_from_radius(self, r, star):
        v_init, v_end, r_mid, exp = self.short(r, star)
        dvdr = (self.steepness * (v_end - v_init) * exp
                / (r_mid * (1. + exp)**2))
        v = v_init + (v_end - v_init) / (1. + exp)
        acc = v * dvdr
        return self.fix_acc_cutoff(r, acc, star)

    def velocity_from_radius(self, r, star):
        v_init, v_end, r_mid, exp = self.short(r, star)
        v = v_init + (v_end - v_init) / (1. + exp)
        return self.fix_v_cutoff(r, v, star)


class AcceleratingWind(SimpleWind):
    """
       This wind model returns SPH particles moving away from the star at sub
       terminal velocity. It also adds a potential around the star that
       represents the radiation pressure. This potential can accelerate all
       particles away from the star using bridge. This is good for simulating
       processes within a few stellar radii.
    """

    acc_functions = {"rsquared": RSquaredAcceleration,
                     "delayed_rsquared": DelayedRSquaredAcceleration,
                     "constant_velocity": ConstantVelocityAcceleration,
                     "velocity_law": VelocityLawAcceleration,
                     "nowotny": NowotnyAcceleration,
                     "logistic": LogisticVelocityAcceleration,
                     }

    def __init__(self, *args, **kwargs):
        r_out_ratio = kwargs.pop("r_out_ratio", 5)
        acc_start_ratio = kwargs.pop("acc_start_ratio", 2)
        grav_r_out_ratio = kwargs.pop("grav_r_out_ratio", 10)
        acc_func = kwargs.pop("acceleration_function", "constant_velocity")
        acc_func_args = kwargs.pop("acceleration_function_args", {})
        self.critical_time_step = kwargs.pop("critical_time_step", None)
        self.v_init_ratio = kwargs.pop("v_init_ratio", None)
        self.compensate_pressure = kwargs.pop("compensate_pressure", False)
        self.add_atmospheric_pressure = kwargs.pop("add_atmospheric_pressure",
                                                   False)
        self.staging_radius = kwargs.pop("staging_radius", None)

        super(AcceleratingWind, self).__init__(*args, **kwargs)

        if isinstance(acc_func, basestring):
            acc_func = self.acc_functions[acc_func]

        self.acc_function = acc_func(**acc_func_args)

        self.particles.add_calculated_attribute(
            "acc_cutoff", lambda r: r_out_ratio * r,
            attributes_names=['radius'])

        self.particles.add_calculated_attribute(
            "acc_start", lambda r: acc_start_ratio * r,
            attributes_names=['radius'])

        self.particles.add_calculated_attribute(
            "grav_acc_cutoff", lambda r: grav_r_out_ratio * r,
            attributes_names=['radius'])

        self.internal_energy_formula = self.scaled_u_from_T
        self.gamma = 5./3.

    def set_initial_wind_velocity(self):
        if self.v_init_ratio is not None:
            self.particles.add_calculated_attribute(
                "initial_wind_velocity", lambda v: self.v_init_ratio * v,
                attributes_names=['terminal_wind_velocity'])

    def scaled_u_from_T(self, star, wind=None):
        """
            set the internal energy from the stellar surface temperature.
        """
        u_0 = (3./2. * constants.kB * star.temperature / star.mu)
        if wind is None:
            return u_0

        m_dot = star.wind_mass_loss_rate
        v_0 = star.initial_wind_velocity
        rho_0 = m_dot / (4. * numpy.pi * star.radius**2 * v_0)

        r = wind.position.lengths()
        v = wind.velocity.lengths()
        rho = m_dot / (4. * numpy.pi * r**2 * v)

        u = rho_0**(1 - self.gamma) * rho**(self.gamma - 1) * u_0
        return u

    def wind_sphere(self, star, Ngas):
        wind = Particles(Ngas)

        dt = (self.model_time - star.wind_release_time)
        if self.critical_time_step is None or dt > self.critical_time_step:
            acc_function = self.acc_function
        else:
            acc_function = ConstantVelocityAcceleration()

        outer_wind_distance = acc_function.radius_from_time(dt, star)

        wind.position, direction = self.generate_positions(
            Ngas, star.radius, outer_wind_distance,
            acc_function.radius_from_number, star=star)

        velocities = acc_function.velocity_from_radius(
            wind.position.lengths(), star)
        wind.velocity = direction * self.as_three_vector(velocities)

        return wind

    def pressure_accelerations(self, indices, radii, star):
        v = self.acc_function.velocity_from_radius(radii, star)
        a = self.acc_function.acceleration_from_radius(radii, star)
        u = self.internal_energy_formula(star)
        m_dot = star.wind_mass_loss_rate
        v_init = star.initial_wind_velocity

        rho = m_dot / (4 * numpy.pi * v * radii**2)
        rho_init = m_dot / (4. * numpy.pi * v_init * star.radius**2)

        k = (self.gamma-1) * rho_init**(1-self.gamma) * u

        dvdr = a/v

        acceleration = self.gamma * k * rho**(self.gamma-1) * (2./radii + dvdr/v)

        return acceleration

    def radial_velocities(self, gas, star):
        rad_velocity = [] | units.ms
        pos_vel = zip(gas.position-star.position, gas.velocity-star.velocity)
        for pos, vel in pos_vel:
            rad_direction = pos/pos.length()
            scalar_projection = vel.dot(rad_direction)

            rad_velocity.append(scalar_projection)

        return rad_velocity

    def staging_accelerations(self, indices, radii, star):
        particles = self.the_target_gas[indices]
        v_now = self.radial_velocities(particles, star)
        v_target = self.acc_function.velocity_from_radius(radii, star)
        dt = self.bridge_time_step
        acc = (v_target - v_now) / dt
        return acc

    def atmospheric_pressure(self, indices, radii, star):
        v = self.acc_function.velocity_from_radius(radii, star)
        g = constants.G * star.mass/star.radius**2
        h = (constants.kB * star.temperature)/(g*star.mu)
        rho = star.wind_mass_loss_rate / (4 * numpy.pi * v * radii**2)
        s_v = star.initial_wind_velocity
        s_r = star.radius
        rho_surface = star.wind_mass_loss_rate / (4 * numpy.pi * s_v * s_r**2)

        pressure_surface = (rho_surface * constants.kB
                            * star.temperature)/star.mu
        acceleration = (pressure_surface / (rho * h)
                        * numpy.exp(-(radii-star.radius)/h))
        return acceleration

    def acceleration(self, star, radii):
        accelerations = numpy.zeros(radii.shape) | units.m/units.s**2

        i_acc = ((radii >= star.radius) & (radii < star.acc_cutoff))
        i_all = radii < star.acc_cutoff
        i_all_grav = radii < star.grav_acc_cutoff

        accelerations[i_acc] += self.acc_function.acceleration_from_radius(
            radii[i_acc], star)

        if self.compensate_pressure:
            if self.staging_radius is not None:
                i_pres = radii > star.radius * self.staging_radius
            else:
                i_pres = i_all
            accelerations[i_pres] -= self.pressure_accelerations(
                i_pres, radii[i_pres], star)

        if self.compensate_gravity:
            r = radii[i_all_grav]
            accelerations[i_all_grav] += constants.G * star.mass / r**2

        if self.add_atmospheric_pressure:
            i_star = radii < star.radius
            acc_atm = self.atmospheric_pressure(i_star, radii[i_star], star)
            accelerations[i_star] += acc_atm

        if self.staging_radius is not None:
            i_stag = radii < star.radius * self.staging_radius
            if i_stag.any():
                accelerations[i_stag] += self.staging_accelerations(
                    i_stag, radii[i_stag], star)

        return accelerations

    def get_gravity_at_point(self, eps, x, y, z):
        total_acceleration = (
            numpy.zeros(shape=(len(x), 3)) | units.m/units.s**2)

        positions = quantities.as_vector_quantity(
            numpy.transpose([x, y, z]))
        for star in self.particles:
            relative_position = positions - star.position
            distance = relative_position.lengths()
            acceleration = self.acceleration(star, distance)
            direction = relative_position / self.as_three_vector(distance)
            # Correct for directionless vectors with length 0
            direction[numpy.isnan(direction)] = 0
            total_acceleration += direction * self.as_three_vector(acceleration)

        return total_acceleration.transpose()


class MechanicalLuminosityWind(SimpleWind):
    """
        This wind model returns SPH particles that have no initial velocity
        with respect to the star. The energy of the integrated mechanical
        luminosity is added as internal energy. This is a numerical
        integration, so the timescale with which evolve_model is called should
        be small enough for convergence.

        This method good for simulating processes far from the star, and when
        the SPH particle mass is larger then the stellar mass loss per
        timestep.  It can make a big difference when the wind is derived from
        evolution.
    """

    def __init__(self, *args, **kwargs):
        self.feedback_efficiency = kwargs.pop("feedback_efficiency", 0.01)
        self.r_max = kwargs.pop("r_max", None)
        self.r_max_ratio = kwargs.pop("r_max_ratio", 5)
        super(MechanicalLuminosityWind, self).__init__(*args, **kwargs)

        self.internal_energy_formula = self.mechanical_internal_energy

        self.previous_time = 0 | units.Myr
        self.particles.track_mechanical_energy(True)

    def evolve_particles(self):
        self.particles.evolve_mass_loss(self.model_time)

    def mechanical_internal_energy(self, star, wind):
        mass_lost = wind.mass.sum()
        mechanical_energy_to_remove = star.mechanical_energy / (
            star.lost_mass/mass_lost + 1)
        star.mechanical_energy -= mechanical_energy_to_remove

        return (self.feedback_efficiency * mechanical_energy_to_remove
                / mass_lost)

    def wind_sphere(self, star, Ngas):
        wind = Particles(Ngas)

        r_max = self.r_max or self.r_max_ratio * star.radius
        wind.position, direction = self.generate_positions(Ngas, star.radius, r_max)
        wind.velocity = [0, 0, 0] | units.kms

        return wind

    def reset(self):
        super(MechanicalLuminosityWind, self).reset()
        self.previous_time = 0 | units.Myr


def new_stellar_wind(sph_particle_mass, target_gas=None, timestep=None,
                     derive_from_evolution=False, mode="simple", **kwargs):
    """
        Create a new stellar wind code.
        target_gas: a gas particle set into which the wind particles should be
            put (requires timestep)
        timestep: the timestep at which the wind particles should be generated.
        derive_from_evolution: derive the wind parameters from stellar
            evolution (you still need to update the stellar parameters)
        mode: set to 'simple', 'accelerate' or 'mechanical'
    """
    if (target_gas is None) ^ (timestep is None):
        raise AmuseException("Must specify both target_gas and timestep"
                             "(or neither)")

    wind_modes = {"simple": SimpleWind,
                  "accelerate": AcceleratingWind,
                  "mechanical": MechanicalLuminosityWind,
                  }

    stellar_wind = wind_modes[mode](sph_particle_mass, derive_from_evolution,
                                    **kwargs)

    if target_gas is not None:
        stellar_wind.set_target_gas(target_gas, timestep)

    return stellar_wind


def static_wind_from_stellar_evolution(stellar_wind, stellar_evolution,
                                       start_time, end_time):
    """
        Convenience method that sets up the stellar wind parameters using a
        stellar evolution code. The change in the stars between start_time and
        end_time determines the stellar wind. Do not add the star particles to
        the stellar_wind code before calling this function.
    """
    stellar_evolution.evolve_model(start_time)
    stellar_wind.particles.add_particles(stellar_evolution.particles)

    stellar_evolution.evolve_model(end_time)
    chan = stellar_evolution.particles.new_channel_to(stellar_wind.particles)
    chan.copy_attributes(["age", "radius", "mass", "luminosity",
                          "temperature"])
    stellar_wind.evolve_model(0 | units.yr)
    stellar_wind.reset()

    return stellar_wind
