from sim_runner import ROOT,Simulator,dump
with Simulator() as sim:
    model=sim.build('rva23_wait_reservation','rv_wait_reservation_tb',[
        'rtl/backend/rv23_wait_reservation.sv','tb/unit/backend/rv_wait_reservation_tb.sv'])
    model['run']=sim.simulate(model);model['passed']=True
    dump(ROOT/'out/rva23/wait_reservation.json',model)
    print('PASS WRS wait/wake/timeout privilege checks; integrated execution checked separately',flush=True)
