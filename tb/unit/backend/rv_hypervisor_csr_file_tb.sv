`timescale 1ns/1ps
module rv_hypervisor_csr_file_tb;
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
    .fp_state_write_i(fp_dirty),.vector_state_write_i(vector_dirty),.vector_vl_i(64'd4),.fflags_accrue_valid_i(1'b0),.fflags_accrue_i(5'b0),.flush_all_i(1'b0),
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
  task automatic check_envcfg_and_external_pending;
    logic [63:0] machine_env,supervisor_env,hypervisor_env,pending_read;
    write_csr(12'h30a,1);write_csr(12'h10a,1);write_csr(12'h60a,1);
    read_csr(12'h30a,machine_env);read_csr(12'h10a,supervisor_env);read_csr(12'h60a,hypervisor_env);
    // SEIP reads B|E, but an unrelated CSRRS must update B using B alone.
    // Drop external E after commit: it must not leave a software interrupt.
    write_csr(12'h344,0);seip=1;
    @(negedge clk);address=12'h344;command=CSR_CMD_SET;operand=2;rs_zero=0;csr_valid=1;csr_execute=1;#1;
    if(illegal || !rdata[9])$fatal(1,"external SEIP not visible during CSRRS read");
    tick();csr_valid=0;csr_execute=0;csr_commit=1;tick();csr_commit=0;seip=0;tick();
    read_csr(12'h344,pending_read);
    if(machine_env!=1 || supervisor_env!=1 || hypervisor_env!=1 || pending_read!=2)
      $fatal(1,"FIOM/SEIP contract Menv%h Senv%h Henv%h pending%h expected1/1/1/2",machine_env,supervisor_env,hypervisor_env,pending_read);
    // CSRRC must likewise avoid copying external E while preserving B.
    write_csr(12'h344,2);seip=1;
    @(negedge clk);address=12'h344;command=CSR_CMD_CLEAR;operand=2;rs_zero=0;csr_valid=1;csr_execute=1;#1;
    if(illegal || !rdata[9])$fatal(1,"external SEIP not visible during CSRRC read");
    tick();csr_valid=0;csr_execute=0;csr_commit=1;tick();csr_commit=0;seip=0;tick();
    expect_csr(12'h344,0);
    write_csr(12'h344,512);seip=1;
    @(negedge clk);address=12'h344;command=CSR_CMD_CLEAR;operand=2;rs_zero=0;csr_valid=1;csr_execute=1;
    tick();csr_valid=0;csr_execute=0;csr_commit=1;tick();csr_commit=0;seip=0;tick();
    expect_csr(12'h344,512);
    write_csr(12'h344,0);write_csr(12'h30a,0);write_csr(12'h10a,0);write_csr(12'h60a,0);
    $display("PASS writable M/S/H FIOM and external SEIP CSRRS/CSRRC isolation");
  endtask
  task automatic check_machine_interrupt_priorities;
    logic [63:0] pending_value;
    int expected_cause;
    // From low to high priority: LCOFI, STI, SSI, SEI, MTI, MSI, MEI.
    // In particular, non-delegated supervisor sources must keep their
    // architectural cause numbers when delivered to M-mode.
    write_csr(12'h303,0);write_csr(12'h304,64'h2aaa);write_csr(12'h300,8);
    for(int bits=1;bits<128;bits++)begin
      pending_value=(64'(bits[0])<<13)|(64'(bits[1])<<5)|(64'(bits[2])<<1)|(64'(bits[3])<<9);
      msip=bits[5];mtip=bits[4];meip=bits[6];
      write_csr(12'h344,pending_value);
      expected_cause=13;
      if(bits[1])expected_cause=5;
      if(bits[2])expected_cause=1;
      if(bits[3])expected_cause=9;
      if(bits[4])expected_cause=7;
      if(bits[5])expected_cause=3;
      if(bits[6])expected_cause=11;
      #1;if(!interrupt_pending || interrupt_cause!=6'(expected_cause))
        $fatal(1,"M-target IRQ priority bits%h cause%0d expected%0d",bits,interrupt_cause,expected_cause);
      checks++;
    end
    msip=0;mtip=0;meip=0;
    write_csr(12'h344,0);write_csr(12'h304,0);write_csr(12'h300,0);
    $display("PASS all 127 nonempty M-target physical interrupt combinations");
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
  task automatic check_system_permissions;
    logic [63:0] status_value,hstatus_value;
    logic [1:0] target_priv;
    logic target_virtual;
    int expected_sret,expected_sfence,expected_wfi;
    // Exhaust all six independent M/H intercept bits in every real/guest
    // privilege context. Machine TSR/TVM do not intercept guest SRET/SFENCE;
    // machine TW takes priority over a virtual-instruction WFI exception.
    for(int mode_index=0;mode_index<5;mode_index++)begin
      target_priv=mode_index==0?PRIV_M:(mode_index inside {1,3}?PRIV_S:PRIV_U);
      target_virtual=mode_index>=3;
      for(int bits=0;bits<64;bits++)begin
        rst=0;tick();rst=1;tick();
        hstatus_value=(64'(bits[3])<<22)|(64'(bits[4])<<20)|(64'(bits[5])<<21);
        status_value=(64'(bits[0])<<22)|(64'(bits[1])<<20)|(64'(bits[2])<<21)|
          (64'(target_priv)<<11)|(64'(target_virtual)<<39);
        write_csr(12'h600,hstatus_value);write_csr(12'h300,status_value);
        if(target_priv!=PRIV_M)begin
          mret_valid=1;mret_commit=1;tick();mret_valid=0;mret_commit=0;tick();
        end
        if(privilege!=target_priv || virtual_mode!=target_virtual)$fatal(1,"permission matrix entry mode%0d",mode_index);
        expected_sret=target_virtual?((target_priv==PRIV_U || bits[3])?22:0):
          ((target_priv==PRIV_U || target_priv==PRIV_S && bits[0])?2:0);
        expected_sfence=target_virtual?((target_priv==PRIV_U || bits[4])?22:0):
          ((target_priv==PRIV_U || target_priv==PRIV_S && bits[1])?2:0);
        expected_wfi=target_priv!=PRIV_M && bits[2]?2:
          (target_virtual && (target_priv==PRIV_U || bits[5])?22:(target_priv==PRIV_U?2:0));
        sret_valid=1;sfence_valid=1;wfi_valid=1;#1;
        if(sret_illegal!=(expected_sret!=0) || expected_sret!=0 && sret_cause!=6'(expected_sret) ||
           sfence_illegal!=(expected_sfence!=0) || expected_sfence!=0 && sfence_cause!=6'(expected_sfence) ||
           wfi_illegal!=(expected_wfi!=0) || expected_wfi!=0 && wfi_cause!=6'(expected_wfi))
          $fatal(1,"permission matrix mode%0d bits%h SRET%0d/%0d SFENCE%0d/%0d WFI%0d/%0d",mode_index,bits,
            sret_illegal?sret_cause:0,expected_sret,sfence_illegal?sfence_cause:0,expected_sfence,wfi_illegal?wfi_cause:0,expected_wfi);
        sret_valid=0;sfence_valid=0;wfi_valid=0;checks+=3;
      end
    end
    rst=0;tick();rst=1;tick();
    $display("PASS system permission matrix 320 contexts / 960 SRET-SFENCE-WFI checks");
  endtask
  logic [63:0] value;
  always @(posedge clk)if(trap_valid)$display("H_EVENT time%0t cause%0d priv%0d V%0d targetS%0d targetVS%0d",$time,trap_cause,privilege,virtual_mode,dut.trap_to_s,dut.h_to_vs);
  initial begin
    repeat(4)@(negedge clk);rst=1;tick();
    check_system_permissions();
    check_envcfg_and_external_pending();
    check_machine_interrupt_priorities();
    for (int entry=8;entry<16;entry++) begin
      expect_csr(12'(12'h3b0+entry),0);
      write_csr(12'(12'h3b0+entry),64'hffffffffffffffff);
      expect_csr(12'(12'h3b0+entry),0);
    end
    write_csr(12'h3a2,64'hffffffffffffffff);expect_csr(12'h3a2,0);
    read_csr(12'h3a1,value,2);
    expect_csr(12'hf15,0);write_csr(12'hf15,0,2);
    read_csr(12'h301,value);if(!value[7] || !value[21] || !value[3])$fatal(1,"H/V/D misa bits");
    expect_csr(12'h303,64'h444);write_csr(12'h303,0);expect_csr(12'h303,64'h444);
    write_csr(12'h303,64'h200);write_csr(12'h304,64'ha00);write_csr(12'h302,64'hf0b7ff);
    write_csr(12'h105,64'h80004001);write_csr(12'h141,64'h80003000);
    write_csr(12'h306,7);write_csr(12'h106,7);
    write_csr(12'h30a,64'hc000000000000000);write_csr(12'h60a,64'hc000000000000000);
    write_csr(12'h606,7);write_csr(12'h602,64'h2104);write_csr(12'h603,64'h444);
    write_csr(12'h60c,64'hc000000000000000);
    write_csr(12'h200,64'h2222);write_csr(12'h205,64'h40003001);write_csr(12'h240,64'h12345678);
    write_csr(12'h280,64'h8000000000010000);write_csr(12'h680,64'h8000000000080000);
    write_csr(12'h605,64'hfffffffffffffff6);write_csr(12'h24d,91);
    enter_guest();
    expect_csr(12'h140,64'h12345678);expect_csr(12'h180,64'h8000000000010000);
    expect_csr(12'hc01,64'hfffffffffffffff6);expect_csr(12'hc20,4);
    read_csr(12'h600,value,22);read_csr(12'h240,value,22);read_csr(12'h300,value,2);
    write_csr(12'h100,64'h200);read_csr(12'h001,value,2);
    write_csr(12'h100,64'h2222);write_csr(12'h001,0);
    if(mstatus[14:13]!=3 || vsstatus[14:13]!=3)$fatal(1,"both FS dirty on guest FCSR write");
    vector_dirty=1;tick();vector_dirty=0;tick();
    if(mstatus[10:9]!=3 || vsstatus[10:9]!=3)$fatal(1,"both VS dirty");
    guest_va=1;take_trap(13,0,64'h40003000);
    if(!virtual_mode || privilege!=PRIV_S)$fatal(1,"VS delegated trap context");
    expect_csr(12'h141,trap_pc);expect_csr(12'h142,13);expect_csr(12'h143,trap_tval);
    if(sret_pc!=trap_pc)$fatal(1,"VS SRET PC");sreturn();
    write_csr(12'h104,64'h20);mtime=100;#1;
    if(interrupt_pending)$fatal(1,"virtual timer early");
    mtime=101;#1;if(!interrupt_pending || interrupt_cause!=6)$fatal(1,"guest timer interrupt eligibility");
    guest_va=0;take_trap(6,1,64'h40003014);
    expect_csr(12'h142,64'h8000000000000005);expect_csr(12'h141,trap_next);
    write_csr(12'h14d,1000);sreturn();
    seip=1;#1;if(!interrupt_pending || interrupt_cause!=9)$fatal(1,"HS interrupt must preempt VS with HS SIE off");
    take_trap(9,1,64'h80004024);seip=0;
    if(virtual_mode || privilege!=PRIV_S || !hstatus[7] || !hstatus[8])$fatal(1,"HS interrupt guest context");
    expect_csr(12'h141,trap_next);expect_csr(12'h241,64'h40002008);
    sreturn();if(!virtual_mode || privilege!=PRIV_S)$fatal(1,"HS SRET guest context");
    guest_address=64'h123456780;implicit_access=1;guest_va=1;
    take_trap(21,0,64'h80004000);
    if(virtual_mode || !hstatus[7] || !hstatus[6])$fatal(1,"guest fault HS context");
    expect_csr(12'h643,guest_address>>2);expect_csr(12'h64a,64'h3000);
    sreturn();write_csr(12'h106,0);write_csr(12'h100,64'h2200);write_csr(12'h141,64'h40004000);
    sreturn();if(privilege!=PRIV_U || !virtual_mode)$fatal(1,"VS SRET VU context");
    read_csr(12'h100,value,22);read_csr(12'hc00,value,22);
    sfence_valid=1;sret_valid=1;wfi_valid=1;#1;
    if(!sfence_illegal || sfence_cause!=22 || !sret_illegal || sret_cause!=22 || !wfi_illegal || wfi_cause!=22)$fatal(1,"VU privileged instruction causes");
    sfence_valid=0;sret_valid=0;wfi_valid=0;
    meip=1;#1;if(!interrupt_pending || interrupt_cause!=11)$fatal(1,"M interrupt must preempt VU");
    guest_va=0;implicit_access=0;take_trap(11,1,64'h80000000);meip=0;
    if(privilege!=PRIV_M || virtual_mode || !mstatus[39] || mstatus[12:11]!=PRIV_U)
      $fatal(1,"M trap saves guest MPV/MPP: priv%0d V%0d status%h mpv%0d",privilege,virtual_mode,mstatus,dut.h_mpv);
    write_csr(12'h306,0);mret_valid=1;mret_commit=1;tick();mret_valid=0;mret_commit=0;tick();
    read_csr(12'hc00,value,2);if(privilege!=PRIV_U || !virtual_mode)$fatal(1,"MRET VU restore");
    $display("PASS rv_hypervisor_csr_file_tb checks=%0d committed H/VS CSR/interrupt/trap/return paths",checks);$finish;
  end
  initial begin #1000000;$fatal(1,"H CSR file watchdog");end
endmodule
