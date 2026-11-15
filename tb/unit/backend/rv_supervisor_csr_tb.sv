`timescale 1ns/1ps
module rv_supervisor_csr_tb;
  import rv_ooo_pkg::*;
  logic clk=0,rst=0;
  always #5 clk=~clk;
  logic csr_valid=0,csr_execute=0,csr_commit=0,rs_zero=0;
  logic [11:0] address=0;
  csr_cmd_e command=CSR_CMD_WRITE;
  logic [63:0] operand=0,rdata;
  logic illegal,write_effect;
  logic trap_valid=0,trap_interrupt=0;
  logic [63:0] trap_pc=0,trap_tval=0,trap_next=0,trap_vector;
  logic [5:0] trap_cause=0,interrupt_cause;
  logic mret_valid=0,mret_commit=0,sret_valid=0,sret_commit=0;
  logic mret_illegal,sret_illegal,sfence_valid=0,sfence_illegal;
  logic [63:0] mret_pc,sret_pc,mstatus,satp,menvcfg,senvcfg;
  privilege_e privilege;
  logic msip=0,mtip=0,meip=0,seip=0,interrupt_pending,wfi_wake;
  logic [63:0] mtime=0;
  logic [1:0] retire_count=0;
  int checks=0;
  rv_csr_file #(.XLEN(64),.PADDR_WIDTH(32),.HAS_SMODE(1),.HAS_B(1),.HAS_SSNPM(1),.HAS_CBO(1)) dut (
    .clk_i(clk),.rst_ni(rst),.csr_valid_i(csr_valid),.csr_execute_i(csr_execute),.csr_commit_i(csr_commit),
    .csr_addr_i(address),.csr_cmd_i(command),.csr_operand_i(operand),.csr_rs1_is_zero_i(rs_zero),
    .csr_ready_o(),.csr_rdata_o(rdata),.csr_illegal_o(illegal),.csr_write_effect_o(write_effect),
    .trap_valid_i(trap_valid),.trap_ready_o(),.trap_pc_i(trap_pc),.trap_cause_i(trap_cause),
    .trap_tval_i(trap_tval),.trap_is_interrupt_i(trap_interrupt),.trap_next_pc_i(trap_next),.trap_vector_o(trap_vector),
    .mret_valid_i(mret_valid),.mret_commit_i(mret_commit),.mret_ready_o(),.mret_pc_o(mret_pc),.mret_illegal_o(mret_illegal),
    .sret_valid_i(sret_valid),.sret_commit_i(sret_commit),.sret_pc_o(sret_pc),.sret_illegal_o(sret_illegal),
    .sfence_valid_i(sfence_valid),.sfence_illegal_o(sfence_illegal),
    .wfi_valid_i(1'b0),.wfi_illegal_o(),.wfi_wake_o(wfi_wake),
    .irq_software_i(msip),.irq_timer_i(mtip),.irq_external_i(meip),.irq_supervisor_external_i(seip),.mtime_i(mtime),
    .interrupt_pending_o(interrupt_pending),.interrupt_cause_o(interrupt_cause),.retire_count_i(retire_count),
    .fflags_accrue_valid_i(1'b0),.fflags_accrue_i(5'b0),.flush_all_i(1'b0),
    .privilege_o(privilege),.mstatus_o(mstatus),.mtvec_o(),.mepc_o(),.frm_o(),.fflags_o(),
    .satp_o(satp),.menvcfg_o(menvcfg),.senvcfg_o(senvcfg),.pmpcfg_o(),.pmpaddr_o());
  task automatic tick;@(posedge clk);#1;@(negedge clk);endtask
  task automatic read_csr(input logic [11:0] a,output logic [63:0] value,input bit expect_illegal=0);
    address=a;command=CSR_CMD_SET;operand=0;rs_zero=1;csr_valid=1;#1;
    if(illegal!==expect_illegal) $fatal(1,"S CSR read privilege=%d addr=%h illegal=%b",privilege,a,illegal);
    value=rdata;csr_valid=0;checks++;
  endtask
  task automatic write_csr(input logic [11:0] a,input logic [63:0] value);
    address=a;command=CSR_CMD_WRITE;operand=value;rs_zero=value==0;csr_valid=1;csr_execute=1;#1;
    if(illegal) $fatal(1,"S CSR write privilege=%d addr=%h",privilege,a);
    tick();csr_valid=0;csr_execute=0;csr_commit=1;tick();csr_commit=0;tick();checks++;
  endtask
  task automatic mreturn(input privilege_e target,input logic [63:0] pc);
    write_csr(12'h341,pc);write_csr(12'h300,64'(target)<<11);
    mret_valid=1;mret_commit=1;#1;
    if(mret_illegal || mret_pc!==pc) $fatal(1,"MRET target");
    tick();mret_valid=0;mret_commit=0;tick();
    if(privilege!==target) $fatal(1,"MRET privilege");checks++;
  endtask
  task automatic take_trap(input logic [5:0] cause,input bit interrupt_kind,input logic [63:0] vector);
    trap_pc=64'h80001236;trap_next=64'h8000123a;trap_tval=64'hfeedface00123456;
    trap_cause=cause;trap_interrupt=interrupt_kind;trap_valid=1;#1;
    if(trap_vector!==vector) $fatal(1,"Trap vector cause=%d got=%h expected=%h",cause,trap_vector,vector);
    tick();trap_valid=0;tick();checks++;
  endtask
  logic [63:0] value,before_value;
  initial begin
    repeat(4) @(negedge clk);rst=1;tick();
    read_csr(12'h301,value);if(!value[18] || !value[1] || value[63:62]!=2) $fatal(1,"MISA S/B/MXL");
    read_csr(12'h100,value);if(value[33:32]!=2) $fatal(1,"Ssu64xl UXL");
    write_csr(12'h180,64'h8000123400080000);read_csr(12'h180,value);
    if(value!==64'h8000123400080000 || satp!==value) $fatal(1,"SATP Sv39");
    write_csr(12'h180,64'h9000567800080001);read_csr(12'h180,value);
    if(value!==64'h8000123400080000) $fatal(1,"SATP unsupported mode must ignore entire write");
    write_csr(12'h180,0);
    write_csr(12'h302,64'h100);write_csr(12'h105,64'h80004000);
    mreturn(PRIV_U,64'h80008000);
    sfence_valid=1;sret_valid=1;#1;
    if(!sfence_illegal || !sret_illegal) $fatal(1,"U SFENCE/SRET permission");
    sfence_valid=0;sret_valid=0;
    read_csr(12'h100,value,1);
    take_trap(8,0,64'h80004000);
    if(privilege!=PRIV_S || mstatus[8] || mstatus[1]) $fatal(1,"U ECALL delegation state");
    read_csr(12'h141,value);if(value!==trap_pc || sret_pc!==trap_pc) $fatal(1,"SEPC");
    read_csr(12'h142,value);if(value!==8) $fatal(1,"SCAUSE");
    read_csr(12'h143,value);if(value!==trap_tval) $fatal(1,"STVAL");
    sret_valid=1;sret_commit=1;tick();sret_valid=0;sret_commit=0;tick();
    if(privilege!=PRIV_U || !mstatus[5]) $fatal(1,"SRET returns U");
    take_trap(2,0,64'h80000000);
    if(privilege!=PRIV_M) $fatal(1,"Undelegated exception must enter M");
    write_csr(12'h300,64'h200008); // MIE + TVM; SSTATUS must not alter either.
    write_csr(12'h100,64'hffffffffffffffff);read_csr(12'h300,value);
    if(!value[3] || !value[21] || value[12:11]!=0) $fatal(1,"SSTATUS changed machine fields");
    write_csr(12'h300,64'h100800);write_csr(12'h341,64'h80008000);
    mret_valid=1;mret_commit=1;tick();mret_valid=0;mret_commit=0;tick();
    read_csr(12'h180,value,1);sfence_valid=1;#1;
    if(!sfence_illegal) $fatal(1,"TVM did not block SFENCE");sfence_valid=0;
    take_trap(2,0,64'h80000000);
    write_csr(12'h306,7);write_csr(12'h106,7);
    write_csr(12'h30a,64'h8000000000000000);
    write_csr(12'h14d,64'd100);write_csr(12'h303,64'h20);
    write_csr(12'h304,64'h820);write_csr(12'h105,64'h80004001);
    mreturn(PRIV_S,64'h80008000);mtime=100;#1;
    if(interrupt_pending || !wfi_wake) $fatal(1,"S timer global enable/WFI wake");
    write_csr(12'h100,64'h2);#1;
    if(!interrupt_pending || interrupt_cause!=5) $fatal(1,"Sstc interrupt not selected");
    take_trap(5,1,64'h80004014);
    if(privilege!=PRIV_S || !mstatus[8] || mstatus[1] || !mstatus[5]) $fatal(1,"S interrupt state");
    read_csr(12'h141,value);if(value!==trap_next) $fatal(1,"Interrupt SEPC must use next PC");
    read_csr(12'h142,value);if(value!==64'h8000000000000005) $fatal(1,"Interrupt SCAUSE");
    write_csr(12'h14d,1000);#1;if(wfi_wake) $fatal(1,"Sstc compare update failed");
    sret_valid=1;sret_commit=1;tick();sret_valid=0;sret_commit=0;tick();
    meip=1;#1;if(!interrupt_pending || interrupt_cause!=11) $fatal(1,"M interrupt at S privilege");
    take_trap(11,1,64'h80000000);meip=0;
    write_csr(12'h320,5);retire_count=2;read_csr(12'hb00,before_value);
    repeat(8) tick();read_csr(12'hb00,value);if(value!==before_value) $fatal(1,"mcountinhibit.CY");
    read_csr(12'hb02,before_value);repeat(8) tick();read_csr(12'hb02,value);
    if(value!==before_value) $fatal(1,"mcountinhibit.IR");retire_count=0;
    read_csr(12'hb03,value);if(value!=0) $fatal(1,"HPM zero counter");
    read_csr(12'h323,value);if(value!=0) $fatal(1,"HPM zero event");
    read_csr(12'hda0,value);if(value!=0) $fatal(1,"HPM overflow zero");
    write_csr(12'h10a,64'h2000000f0);
    read_csr(12'h10a,value);if(value!==64'h2000000f0)$fatal(1,"Ssnpm PMLEN7 enable");
    write_csr(12'h10a,64'h100000010);
    read_csr(12'h10a,value);if(value!==64'h200000010)$fatal(1,"Ssnpm reserved WARL PMM");
    write_csr(12'h10a,64'h300000040);
    read_csr(12'h10a,value);if(value!==64'h200000040)$fatal(1,"Ssnpm unsupported PMLEN16 WARL");
    write_csr(12'h10a,0);read_csr(12'h10a,value);if(value!=0)$fatal(1,"Ssnpm disable");
    $display("PASS rv_supervisor_csr_tb checks=%0d delegation/SRET/Sstc/TVM/counters/Ssnpm",checks);$finish;
  end
  initial begin #100000;$fatal(1,"Supervisor CSR watchdog");end
endmodule
