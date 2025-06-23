#!/usr/bin/env python

"""This is Brewster: the golden retriever of smelly atmospheres"""
from __future__ import print_function

import multiprocessing
import time
import numpy as np
import scipy as sp
import emcee
import testkit
import ciamod
import TPmod
import settings
import os
import gc
import sys
import pickle
from mpi4py import MPI
from scipy import interpolate
from scipy.interpolate import interp1d
from scipy.interpolate import InterpolatedUnivariateSpline
from schwimmbad import MPIPool

__author__ = "Ben Burningham"
__copyright__ = "Copyright 2015 - Ben Burningham"
__credits__ = ["Ben Burningham"]
__license__ = "GPL"
__version__ = "0.1"
__maintainer__ = "Ben Burningham"
__email__ = "burninghamster@gmail.com"
__status__ = "Development"


# This module set up the model arguments the drop these into
# theta(state vector) or runargs

# This version of the brewing file is for Python 3.7
# It requires emcee 3.0rc2 or later 

settings.init()



# Now we set up the MPI bits
world_comm = MPI.COMM_WORLD
node_comm = world_comm.Split_type(MPI.COMM_TYPE_SHARED)
rank = node_comm.Get_rank()



# First get data and parameters for object

# Give the run name
runname = "J1416B_COMBO"

obspec = np.asfortranarray(np.loadtxt("J1416B_COMBINE.txt", dtype='d', unpack='true'))

# Now the wavelength range
w1 = 0.6
w2 = 14.1


#sets the instrument mode to work with jwst data
fwhm = 999

# DISTANCE (in parsecs)
dist = 9.3 #from Gonzales 2020

# How many patches & clouds do we want??
# Must be at least 1 of each, but can turn off cloud below
npatches = 1
nclouds = 1

# set up array for setting patchy cloud answers
do_clouds = np.zeros([npatches], dtype='i')

# Which patchdes are cloudy
do_clouds[:] = 0

# set up cloud detail arrays
cloudnum = np.zeros([npatches, nclouds], dtype='i')
cloudtype = np.zeros([npatches, nclouds], dtype='i')

cloudnum[:, 0] = 0 #set clouds off by smake it equal to zero
cloudtype[:, 0] = 1

# second patch turn off top cloud
# cloudnum[1,0] = 5
# cloudtype[1,0] = 1

# Are we assuming chemical equilibrium, or similarly precomputed gas abundances?
# Or are we retrieving VMRs (0)
chemeq = 0

do_bff = 0

proftype = 2
pfile = "t1700g1000f3.dat"

# set up pressure grids in log(bar) cos its intuitive
logcoarsePress = np.arange(-4.0, 2.5, 0.53)
logfinePress = np.arange(-4.0, 2.4, 0.1)

# but forward model wants pressure in bar
coarsePress = pow(10, logcoarsePress)
press = pow(10, logfinePress)

# Where are the cross sections?
# give the full path
xpath = "/Users/917543996/Linelists/"
xlist = 'gaslistR10K.dat' # The gaslistR10k better. Rox is sampled at 10k (rather than interpolated to 10k), but they don’t fit the data as well

# now the cross sections

# Now list the gases.
# If Na is after K, at the end of the list, alkalis will be tied
# together at Asplund solar ratio. See Line at al (2015)
# Else if K is after Na, they'll be separate

gaslist = ['h2o','ch4','co','co2','nh3','h2s','ph3','k','na']

ngas = len(gaslist)

# some switches for alternative cross sections
# Use Mike's (Burrows) Alkalis?
# Use Allard (=0), Burrow's(=1), and new Allard (=2)
malk = 1
# Use Mike's CH4?
#mch4 = 1

# now set up the EMCEE stuff
# How many dimensions???  Count them up in the p0 declaration. Carefully
ndim = 17

# How many walkers we running?
nwalkers = ndim * 16

# How many burn runs do we want before reset?
nburn = 10000

# How many iterations are we running?
niter = 30000

# Is this a test or restart?
runtest = 1

# Are we writing the arguments to a pickle?
# Set= 0 for no and run,Set = 1 for write and exit (no run); = 2 for write and continue
# option 2 may cause a memory issue and crash a production run
make_arg_pickle = 2

# Where is the output going?
outdir = "/Users/917543996/Saves/J1416B/"


# Are we using DISORT for radiative transfer?
# (HINT: Not in this century)
use_disort = 0

# use the fudge factor / tolerance parameter?
do_fudge = 1

# Names for the final output files:

# full final sampler with likelihoods, chain, bells and whistles
finalout = runname + ".pk1"

# periodic dumps/snapshots
# just the chain
chaindump = runname + "_last_nc.pic"
# The whole thing w/ probs
picdump = runname + "_snapshot.pic"

# Names for status file runtimes
statfile = "status_ball" + runname + ".txt"
rfile = "runtimes_" + runname + ".dat"

# scale factor r2d2 from distance 1 Rj radius
r2d2 = (71492e3) ** 2. / (dist * 3.086e+16) ** 2.

# If we want fresh guess set to 0, total inherit the previous set 1
# inherit plus randomise the VMRs. 2. See below to enter this filename
fresh = 0

p0 = np.empty([nwalkers, ndim])
if (fresh == 0):
    # ----- "Gas" parameters (Includes gases, gravity, logg, scale factor, dlambda, and tolerance parameter) --
    # # For Non-chemical equilibrium
    p0[:, 0] = (0.5 * np.random.randn(nwalkers).reshape(nwalkers)) - 3.5  # H2O
    p0[:, 1] = (0.5 * np.random.randn(nwalkers).reshape(nwalkers)) - 3.7  # CH4
    p0[:, 2] = (0.5 * np.random.randn(nwalkers).reshape(nwalkers)) - 8.3  # CO
    p0[:, 3] = (0.5 * np.random.randn(nwalkers).reshape(nwalkers)) - 8.0  # CO2
    p0[:, 4] = (0.5 * np.random.randn(nwalkers).reshape(nwalkers)) - 4.8  # NH3
    p0[:, 5] = (0.5 * np.random.randn(nwalkers).reshape(nwalkers)) - 8.0  # H2S
    p0[:, 6] = (0.5 * np.random.randn(nwalkers).reshape(nwalkers)) - 10.0  # PH3
    p0[:, 7] = (0.5 * np.random.randn(nwalkers).reshape(nwalkers)) - 10.0  # Na+K
    p0[:, 8] = 0.1 * np.random.randn(nwalkers).reshape(nwalkers) + 4.5  # gravity
    p0[:, 9] = r2d2 + (np.random.randn(nwalkers).reshape(nwalkers) * (0.1 * r2d2))  # scale factor 1
    p0[:, 10] = np.random.randn(nwalkers).reshape(nwalkers) * 0.001  # dlambda
    p0[:, 11] = np.log10((np.random.rand(nwalkers).reshape(nwalkers) * (max(obspec[2, :] ** 2) * (0.1 - 0.01))) + (
                0.01 * min(obspec[2, 10::3] ** 2)))  # tolerance parameter 1

    # p0[:, ndim - 6] = 50. + (
    #     np.random.randn(nwalkers).reshape(nwalkers))  # gamma - removes wiggles unless necessary to profile
    # BTprof = np.loadtxt("BTtemp800_45_5.dat")
    # for i in range(0, 5):  # 13 layer points
    #     p0[:, ndim - 5 + i] = (BTprof[i] / 2) + (50. * np.random.randn(nwalkers).reshape(nwalkers))
    #
    # for i in range(0, nwalkers):
    #     while True:
    #         Tcheck = TPmod.set_prof(proftype, coarsePress, press, p0[i, ndim - 5:])
    #         if min(Tcheck) > 1.0:
    #             break
    #         else:
    #             for i in range(0, 5):
    #                 p0[:, ndim - 5 + i] = (BTprof[i] / 2) + (50. * np.random.randn(nwalkers).reshape(nwalkers))

    # For profile type 1
    #p0[:, ndim - 14] = 50. + (np.random.randn(nwalkers).reshape(nwalkers))  # gamma - removes wiggles unless necessary to profile
    #BTprof = np.loadtxt("BTtemp800_45_13.dat")
    #for i in range(0, 13):  # 13 layer points
    #    p0[:, ndim - 13 + i] = (BTprof[i] / 2) + (50. * np.random.randn(nwalkers).reshape(nwalkers))

    #for i in range(0, nwalkers):
    #    while True:
    #        Tcheck = TPmod.set_prof(proftype, coarsePress, press, p0[i, ndim - 13:])
    #        if min(Tcheck) > 1.0:
    #            break
    #        else:
    #            for i in range(0, 13):
    #                p0[:, ndim - 13 + i] = (BTprof[i] / 2) + (50. * np.random.randn(nwalkers).reshape(nwalkers))
    # These are for type 2. 
    p0[:,12] = 0.39 + 0.1*np.random.randn(nwalkers).reshape(nwalkers)
    p0[:,13] = 0.14 +0.05*np.random.randn(nwalkers).reshape(nwalkers)
    p0[:,14] = -1.2 + 0.2*np.random.randn(nwalkers).reshape(nwalkers)
    p0[:,15] = 2.25+ 0.2*np.random.randn(nwalkers).reshape(nwalkers)
    p0[:,16] = 4200. + (500.*  np.random.randn(nwalkers).reshape(nwalkers))
    for i in range (0,nwalkers):
        while True:
            Tcheck = TPmod.set_prof(proftype, coarsePress, press, p0[i, ndim-5:])
            if min(Tcheck) > 1.0:
                break
            else:
                p0[i, ndim-5] = 0.39 + 0.01*np.random.randn()
                p0[i, ndim-4] = 0.14 + 0.01*np.random.randn()
                p0[i, ndim-3] = -1.2 + 0.2*np.random.randn()
                p0[i, ndim-2] = 2. + 0.2*np.random.randn()
                p0[i, ndim-1] = 4200. + (200.*np.random.randn())
    # These are for type 3.
# If we're doing profile type 1, we need to replace the last TP entries with
# this stuff.....
# p0[:, ndim-14] = 50. + (np.random.randn(nwalkers).reshape(nwalkers))
# gamma - removes wiggles unless necessary to profile
# BTprof = np.loadtxt("BTtemp800_45_13.dat")
# for i in range(0, 13):  # 13 layer points
#   p0[:,ndim-13 + i] = (BTprof[i] - 200.) + (150. * np.random.randn(nwalkers).reshape(nwalkers))

if (fresh != 0):
    fname = chaindump
    pic = pickle.load(open(fname, 'rb'))
    p0 = pic
    if (fresh == 2):
        for i in range(0, 9):
            p0[:, i] = (np.random.rand(nwalkers).reshape(nwalkers) * 0.5) + p0[:, i]

prof = np.full(13, 100.)
if proftype == 9:
    modP, modT = np.loadtxt(pfile, skiprows=1, usecols=(1, 2), unpack=True)
    tfit = InterpolatedUnivariateSpline(np.log10(modP), modT, k=1)
    prof = tfit(logcoarsePress)

# Now we'll get the opacity files into an array
inlinetemps,inwavenum,gasnum,nwave = testkit.get_gasdetails(gaslist,w1,w2,xpath,xlist)

# Get the cia bits
tmpcia, ciatemps = ciamod.read_cia("CIA_DS_aug_2015.dat", inwavenum)
ciatemps = np.asfortranarray(ciatemps, dtype='float32')

settings.cia, _ = testkit.shared_memory_array(rank, node_comm, (4,ciatemps.size,nwave),'float32')

if (rank == 0):
    # cia = np.asfortranarray(np.empty((4,ciatemps.size,nwave)),dtype='float32')
    settings.cia[:,:,:] = tmpcia[:,:,:nwave].copy() 

del(tmpcia)

# grab BFF and Chemical grids
bff_raw, ceTgrid, metscale, coscale, gases_myP = testkit.sort_bff_and_CE(chemeq, "chem_eq_tables_P3K.pic", press,
                                                                         gaslist)

settings.init()
settings.runargs = gases_myP, chemeq, dist, cloudtype, do_clouds, gasnum, cloudnum, inlinetemps, coarsePress, press, inwavenum, ciatemps, use_disort, fwhm, obspec, proftype, do_fudge, prof, do_bff, bff_raw, ceTgrid, metscale, coscale
npress= press.size
ntemps = inlinetemps.size
# set up shared memory array for linelist
settings.linelist, _ = testkit.shared_memory_array(rank, node_comm, (ngas,npress,ntemps,nwave))

if (rank == 0):
    # Now we'll get the opacity files into an array
    settings.linelist[:,:,:,:] = testkit.get_opacities(gaslist,w1,w2,press,xpath,xlist,malk)


world_comm.Barrier()


# Now we set up the MPI bits
pool = MPIPool()
if not pool.is_master():
    pool.wait()
    sys.exit()

# Write the arguments to a pickle if needed
if (make_arg_pickle > 0):
    pickle.dump(settings.runargs, open(outdir + runname + "_runargs.pic", "wb"))
#    pickle.dump( (settings.linelist, settings.cia) , open(outdir+runname+"_opacities.pic", "wb"))
    if (make_arg_pickle == 1):
        sys.exit()

sampler = emcee.EnsembleSampler(nwalkers, ndim, testkit.lnprob, pool=pool)
# '''
# run the sampler
print("running the sampler")
clock = np.empty(80000)
k = 0
times = open(rfile, "w")
times.close()
if runtest == 0 and fresh == 0:
    pos, prob, state = sampler.run_mcmc(p0, nburn)
    sampler.reset()
    p0 = pos
for result in sampler.sample(p0, iterations=niter):
    clock[k] = time.perf_counter()
    if k > 1:
        tcycle = clock[k] - clock[k - 1]
        times = open(rfile, "a")
        times.write("*****TIME FOR CYCLE*****\n")
        times.write(str(tcycle))
        times.close()
    k = k + 1
    position = result.coords
    f = open(statfile, "w")
    f.write("****Iteration*****")
    f.write(str(k))
    f.write("****Reduced Chi2*****")
    f.write(str(result.log_prob * -2.0 / (obspec.shape[1] / 3.0)))
    f.write("****Accept Fraction*****")
    f.write(str(sampler.acceptance_fraction))
    f.write("*****Values****")
    f.write(str(result.coords))
    f.close()

    if (
            k == 10 or k == 1000 or k == 1500 or k == 2000 or k == 2500 or k == 3000 or k == 3500 or k == 4000 or k == 4500 or k == 5000 or k == 6000 or k == 7000 or k == 8000 or k == 9000 or k == 10000 or k == 11000 or k == 12000 or k == 15000 or k == 18000 or k == 19000 or k == 20000 or k == 21000 or k == 22000 or k == 23000 or k == 24000 or k == 25000 or k == 26000 or k == 27000 or k == 28000 or k == 29000 or k == 30000 or k == 35000 or k == 40000 or k == 45000 or k == 50000 or k == 55000 or k == 60000 or k == 65000):
        chain = sampler.chain
        lnprob = sampler.lnprobability
        output = [chain, lnprob]
        pickle.dump(output, open(outdir + picdump, "wb"))
        pickle.dump(chain[:, k - 1, :], open(chaindump, 'wb'))

# get rid of problematic bit of sampler object
del sampler.__dict__['pool']


def save_object(obj, filename):
    with open(filename, "wb") as output:
        pickle.dump(obj, output, pickle.HIGHEST_PROTOCOL)


pool.close()

save_object(sampler, outdir + finalout)
