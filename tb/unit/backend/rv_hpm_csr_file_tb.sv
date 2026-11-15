`timescale 1ns/1ps
module rv_hpm_csr_file_tb;
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
  logic virtual_mode,fp_dirty=0,vector_dirty=0;
  logic [63:0] hstatus,vsstatus,vsatp,hgatp,henvcfg;
  logic [5:0] csr_cause,sret_cause,sfence_cause,wfi_cause;
  logic [63:0] guest_address=0;
  logic implicit_access=0,guest_va=0;
  logic wfi_valid=0,wfi_illegal;
  logic flush=0,retired_enable=0;

  rv_csr_file #(.XLEN(64),.PADDR_WIDTH(32),.HAS_H(1),.HAS_V(1),.HAS_D(1),.HAS_SMODE(1),.HAS_B(1),.HAS_SSNPM(1),.HAS_CBO(1)) dut (
    .clk_i(clk),.rst_ni(rst),.csr_valid_i(csr_valid),.csr_execute_i(csr_execute),.csr_commit_i(csr_commit),
    .csr_addr_i(address),.csr_cmd_i(command),.csr_operand_i(operand),.csr_rs1_is_zero_i(rs_zero),
    .csr_exception_cause_o(csr_cause),.csr_ready_o(),.csr_rdata_o(rdata),.csr_illegal_o(illegal),.csr_write_effect_o(write_effect),
    .trap_guest_address_i(guest_address),.trap_implicit_guest_access_i(implicit_access),.trap_guest_va_i(guest_va),.trap_valid_i(trap_valid),.trap_ready_o(),.trap_pc_i(trap_pc),.trap_cause_i(trap_cause),
    .trap_tval_i(trap_tval),.trap_is_interrupt_i(trap_interrupt),.trap_next_pc_i(trap_next),.trap_vector_o(trap_vector),
    .mret_valid_i(mret_valid),.mret_commit_i(mret_commit),.mret_ready_o(),.mret_pc_o(mret_pc),.mret_illegal_o(mret_illegal),
    .sret_valid_i(sret_valid),.sret_commit_i(sret_commit),.sret_cause_o(sret_cause),.sfence_cause_o(sfence_cause),.wfi_cause_o(wfi_cause),.sret_pc_o(sret_pc),.sret_illegal_o(sret_illegal),
    .sfence_valid_i(sfence_valid),.sfence_illegal_o(sfence_illegal),
    .wfi_valid_i(wfi_valid),.wfi_illegal_o(wfi_illegal),.wfi_wake_o(wfi_wake),
    .irq_software_i(msip),.irq_timer_i(mtip),.irq_external_i(meip),.irq_supervisor_external_i(seip),.mtime_i(mtime),
    .interrupt_pending_o(interrupt_pending),.interrupt_cause_o(interrupt_cause),.retire_count_i(retire_count),
    .fp_state_write_i(fp_dirty),.vector_state_write_i(vector_dirty),.vector_vl_i(64'd4),.fflags_accrue_valid_i(1'b0),.fflags_accrue_i(5'b0),.flush_all_i(flush),
    .privilege_o(privilege),.mstatus_o(mstatus),.mtvec_o(),.mepc_o(),.frm_o(),.fflags_o(),
    .virtual_o(virtual_mode),.hstatus_o(hstatus),.vsstatus_o(vsstatus),.vsatp_o(vsatp),.hgatp_o(hgatp),.henvcfg_o(henvcfg),.satp_o(satp),.menvcfg_o(menvcfg),.senvcfg_o(senvcfg),.pmpcfg_o(),.pmpaddr_o());
  task automatic tick;@(posedge clk);#1;@(negedge clk);endtask
  task automatic read_csr(input logic[11:0] a,output logic[63:0] value,input int error=0);
    address=a;command=CSR_CMD_SET;operand=0;rs_zero=1;csr_valid=1;#1;
    if(illegal!==(error!=0) || (error!=0 && csr_cause!==6'(error)))$fatal(1,"H CSR read addr%h priv%0d V%0d error%0d/%0d expected%0d",a,privilege,virtual_mode,illegal,csr_cause,error);
    value=rdata;csr_valid=0;checks++;
  endtask
  task automatic expect_csr(input logic[11:0] a,input logic[63:0] expected);
    logic[63:0] value;
    read_csr(a,value);if(value!==expected)$fatal(1,"H CSR addr%h got%h expected%h",a,value,expected);
  endtask
  task automatic write_csr(input logic[11:0] a,input logic[63:0] value,input int error=0);
    @(negedge clk);
    address=a;command=CSR_CMD_WRITE;operand=value;rs_zero=value==0;csr_valid=1;csr_execute=error==0;#1;
    if(illegal!==(error!=0) || (error!=0 && csr_cause!==6'(error)))$fatal(1,"H CSR write addr%h priv%0d V%0d error%0d/%0d expected%0d",a,privilege,virtual_mode,illegal,csr_cause,error);
    tick();csr_valid=0;csr_execute=0;
    if(error==0)begin csr_commit=1;tick();csr_commit=0;end
    tick();checks++;
  endtask
  task automatic enter_guest(input privilege_e target=PRIV_S);
    write_csr(12'h341,64'h40001000);
    write_csr(12'h300,64'h8000002200|(64'(target)<<11));
    mret_valid=1;mret_commit=1;#1;
    if(mret_illegal)$fatal(1,"MRET guest illegal");
    tick();mret_valid=0;mret_commit=0;tick();
    if(privilege!=target || !virtual_mode || mstatus[39])$fatal(1,"MRET guest context failed");checks++;
  endtask
  task automatic take_trap(input int code,input bit irq_kind,input logic[63:0] vector);
    @(negedge clk);
    trap_cause=6'(code);trap_interrupt=irq_kind;trap_pc=64'h40002004;trap_next=64'h40002008;
    trap_tval=irq_kind?64'b0:64'h40005000;trap_valid=1;#1;
    if(trap_vector!==vector)$fatal(1,"H trap vector cause%0d got%h expected%h",code,trap_vector,vector);
    tick();trap_valid=0;tick();checks++;
  endtask
  task automatic sreturn;
    @(negedge clk);
    sret_valid=1;sret_commit=1;#1;if(sret_illegal)$fatal(1,"guest SRET illegal cause%0d",sret_cause);
    tick();sret_valid=0;sret_commit=0;tick();checks++;
  endtask
  logic [63:0] value;
  initial begin
    repeat(4)@(negedge clk);rst=1;tick();
    write_csr(12'h320,64'h78);write_csr(12'h306,'1);write_csr(12'h106,'1);write_csr(12'h606,'1);
    expect_csr(12'h306,64'h7f);expect_csr(12'h106,64'h7f);expect_csr(12'h606,64'h7f);
    write_csr(12'hb03,100);expect_csr(12'hb03,100);expect_csr(12'hc03,100);
    // CSR evaluation is not a write; flush cancels its pending ownership.
    @(negedge clk);address=12'hb03;operand=1000;command=CSR_CMD_WRITE;rs_zero=0;csr_valid=1;csr_execute=1;
    tick();csr_valid=0;csr_execute=0;expect_csr(12'hb03,100);
    flush=1;tick();flush=0;csr_commit=1;tick();csr_commit=0;expect_csr(12'hb03,100);
    write_csr(12'h323,2);write_csr(12'hb03,64'hfffffffffffffffe);
    write_csr(12'h304,64'h2000);write_csr(12'h300,8);
    retired_enable=1;retire_count=2;write_csr(12'h320,64'h70);
    retire_count=0;retired_enable=0;write_csr(12'h320,64'h78);
    expect_csr(12'hda0,8);read_csr(12'h344,value);
    if(!value[13] || !interrupt_pending || interrupt_cause!=13)$fatal(1,"HPM overflow interrupt integration");
    write_csr(12'h344,0);expect_csr(12'hda0,8);
    if(interrupt_pending)$fatal(1,"LCOFIP clear did not clear IRQ");
    write_csr(12'h303,64'h2000);write_csr(12'h344,64'h2000);
    read_csr(12'h344,value);if(!value[13])$fatal(1,"software LCOFIP set");
    write_csr(12'h144,0);read_csr(12'h344,value);
    if(value[13] || interrupt_pending)$fatal(1,"SIP clear left a duplicate software LCOFIP owner");
    // scountovf is masked per counter; accesses to enabled hpmcounter are legal.
    write_csr(12'h306,7);expect_csr(12'hda0,8);write_csr(12'h306,64'h7f);
    write_csr(12'h606,7);write_csr(12'h302,64'hf0b7ff);write_csr(12'h105,64'h80004000);
    enter_guest();
    expect_csr(12'hda0,0);read_csr(12'hc03,value,22);write_csr(12'hc03,1,2);
    take_trap(22,0,64'h80004000);
    expect_csr(12'hda0,8);read_csr(12'hc03,value);
    write_csr(12'h606,64'h7f);sreturn();
    expect_csr(12'hda0,8);read_csr(12'hc03,value);
    write_csr(12'h106,0);write_csr(12'h100,0);write_csr(12'h141,64'h40004000);sreturn();
    if(privilege!=PRIV_U || !virtual_mode)$fatal(1,"VU entry");
    read_csr(12'hc03,value,22);read_csr(12'hb03,value,2);read_csr(12'hda0,value,22);
    $display("PASS rv_hpm_csr_file_tb checks=%0d committed bank/overflow/HS/VS/VU",checks);$finish;
  end
  initial begin #1000000;$fatal(1,"HPM CSR timeout");end
endmodule
