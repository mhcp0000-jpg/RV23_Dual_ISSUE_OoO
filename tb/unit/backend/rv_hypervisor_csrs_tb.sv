`timescale 1ns/1ps
module rv_hypervisor_csrs_tb;
  logic clk=0;always #5 clk=~clk;
  logic rst_n=0,valid=0,write=0,selected,exception,virtual_mode,mpv,gva;
  logic [11:0] address=0;
  logic [63:0] data=0,result,mstatus=0,menvcfg='1,mcounteren=7,mtime=0;
  logic [1:0] privilege=3,return_priv;
  logic [5:0] cause;
  logic mstatus_write=0,mie_write=0,mip_write=0,fp_dirty=0,v_dirty=0;
  logic [63:0] machine_data=0;
  logic trap=0,delegated=0,irq=0,guestva=0,implicit_access=0,to_vs;
  logic [5:0] trap_cause=0;
  logic [63:0] pc=0,next_pc=0,tval=0,gpa=0,vs_vector;
  logic mret=0,sret=0,is_mret=0,return_virtual;
  logic [63:0] return_pc,hs_pc=64'h80001000,m_pc=64'h80002000;
  logic [63:0] hstatus,hedeleg,hideleg,henvcfg,hcounteren,vsstatus,vsatp,hgatp,hip,hie,delta,mtval2,mtinst;
  int checks=0;
  rv_hypervisor_csrs dut(.clk_i(clk),.rst_ni(rst_n),.csr_valid_i(valid),.csr_commit_write_i(write),.csr_write_intent_i(write),
    .csr_address_i(address),.csr_write_data_i(data),.privilege_i(privilege),.mstatus_i(mstatus),.menvcfg_i(menvcfg),
    .mcounteren_i(mcounteren),.mtime_i(mtime),.csr_selected_o(selected),.csr_data_o(result),.csr_exception_o(exception),.csr_cause_o(cause),
    .mstatus_commit_write_i(mstatus_write),.mie_commit_write_i(mie_write),.mip_commit_write_i(mip_write),.machine_write_data_i(machine_data),
    .fp_dirty_i(fp_dirty),.vector_dirty_i(v_dirty),.trap_commit_i(trap),.trap_delegated_i(delegated),.trap_interrupt_i(irq),
    .trap_guest_va_i(guestva),.trap_cause_i(trap_cause),.trap_pc_i(pc),.trap_next_pc_i(next_pc),.trap_tval_i(tval),
    .trap_guest_address_i(gpa),.trap_implicit_guest_access_i(implicit_access),.trap_to_vs_o(to_vs),.vs_trap_vector_o(vs_vector),
    .mret_commit_i(mret),.sret_commit_i(sret),.xret_is_mret_i(is_mret),.hs_return_pc_i(hs_pc),.m_return_pc_i(m_pc),
    .xret_privilege_o(return_priv),.xret_virtual_o(return_virtual),.xret_pc_o(return_pc),.virtual_o(virtual_mode),.mpv_o(mpv),.gva_o(gva),
    .hstatus_o(hstatus),.hedeleg_o(hedeleg),.hideleg_o(hideleg),.henvcfg_o(henvcfg),.hcounteren_o(hcounteren),
    .vsstatus_o(vsstatus),.vsatp_o(vsatp),.hgatp_o(hgatp),.hip_o(hip),.hie_o(hie),.htimedelta_o(delta),.mtval2_o(mtval2),.mtinst_o(mtinst));
  task automatic access(input logic[11:0] addr,input bit wr,input logic[63:0] value,
                        input logic[63:0] expected,input int error=0);
    @(negedge clk);valid=1;write=wr;address=addr;data=value;#1;
    if(!selected || exception!==(error!=0) || (error!=0 && cause!==6'(error)) || (!wr && error==0 && result!==expected))
      $fatal(1,"H CSR addr%h p%0d V%0d write%0d result%h exception%0d/%0d expected%h/%0d",addr,privilege,virtual_mode,wr,result,exception,cause,expected,error);
    @(negedge clk);valid=0;write=0;checks++;
  endtask
  task automatic enter_guest(input logic[1:0] p=1);
    privilege=3;mstatus[12:11]=p;machine_data=64'h8000000000;
    @(negedge clk);mstatus_write=1;@(negedge clk);mstatus_write=0;
    is_mret=1;#1;if(!return_virtual || return_priv!=p || return_pc!=m_pc)$fatal(1,"MRET guest context");
    mret=1;@(negedge clk);mret=0;is_mret=0;privilege=p;
    #1;if(!virtual_mode || mpv)$fatal(1,"MRET V/MPV state");checks++;
  endtask
  task automatic trap_event(input int code,input bit delegated_value,input bit interrupt_value=0,
                             input bit implicit_value=0,input bit gva_value=1);
    @(negedge clk);trap_cause=6'(code);delegated=delegated_value;irq=interrupt_value;
    implicit_access=implicit_value;guestva=gva_value;trap=1;
    @(negedge clk);trap=0;checks++;
  endtask
  initial begin
    repeat(3)@(negedge clk);rst_n=1;
    access(12'h600,0,0,64'h200000000);
    access(12'h600,1,'1,0);access(12'h600,0,0,64'h2007003c0);
    access(12'h600,1,0,0);
    access(12'h600,1,64'h0002000000000000,0);
    access(12'h600,0,0,64'h0002000200000000);
    access(12'h600,1,64'h0003000000000000,0);
    access(12'h600,0,0,64'h0002000200000000);
    access(12'h600,1,0,0);
    access(12'h602,1,'1,0);access(12'h602,0,0,64'hb1ff);
    access(12'h603,1,'1,0);access(12'h603,0,0,64'h444);
    access(12'h606,1,'1,0);access(12'h606,0,0,7);
    access(12'h607,1,'1,0);access(12'h607,0,0,0);
    access(12'he12,0,0,0);access(12'he12,1,0,0,2);
    access(12'h680,1,64'h8fffffff1234567f,0);
    access(12'h680,0,0,64'h80000fff1234567c);
    access(12'h680,1,64'h9000000000000000,0);
    access(12'h680,0,0,64'h80000fff1234567c);
    access(12'h280,1,64'h8abc000000080001,0);
    access(12'h280,0,0,64'h8abc000000080001);
    access(12'h205,1,64'h40001001,0);
    access(12'h241,1,64'h40002003,0);access(12'h241,0,0,64'h40002002);
    access(12'h200,1,64'h2222,0); // VS and FS Initial, SIE/SPIE
    access(12'h240,1,64'h123456789abcdef0,0);
    privilege=1;mstatus[20]=1;
    access(12'h680,0,0,0,2);access(12'h280,0,0,64'h8abc000000080001);mstatus[20]=0;
    access(12'h60a,1,64'hc0000002000000f0,0);access(12'h60a,0,0,64'hc0000002000000f0);
    access(12'h60a,1,64'hc0000003000000e0,0);access(12'h60a,0,0,64'hc0000002000000f0);
    menvcfg=0;access(12'h60a,0,0,64'h00000002000000f0);menvcfg='1;
    access(12'h645,1,64'h444,0);access(12'h644,0,0,64'h444);
    access(12'h604,1,64'h444,0);access(12'h204,0,0,64'h222);
    access(12'h204,1,64'h20,0);access(12'h604,0,0,64'h40);
    access(12'h244,1,0,0);access(12'h645,0,0,64'h440);
    access(12'h645,1,0,0);
    enter_guest();
    access(12'h140,0,0,64'h123456789abcdef0);
    access(12'h140,1,64'hfedcba9876543210,0);
    access(12'h600,0,0,0,22);access(12'h240,0,0,0,22);access(12'h34a,0,0,0,2);
    access(12'h180,0,0,64'h8abc000000080001);
    @(negedge clk);fp_dirty=1;v_dirty=1;@(negedge clk);fp_dirty=0;v_dirty=0;
    #1;if(vsstatus[14:13]!=3 || vsstatus[10:9]!=3 || !vsstatus[63])$fatal(1,"VS dirty status");
    pc=64'h40003456;next_pc=pc+4;tval=64'h40008000;gpa=64'h123456780;
    trap_cause=13;delegated=1;#1;if(!to_vs || vs_vector!=64'h40001000)$fatal(1,"VS delegation/vector");
    trap_event(13,1);#1;if(!virtual_mode)$fatal(1,"VS trap exited guest");
    access(12'h141,0,0,pc);access(12'h142,0,0,13);access(12'h143,0,0,tval);
    #1;if(return_priv!=1 || !return_virtual || return_pc!=pc)$fatal(1,"VS SRET context");
    @(negedge clk);sret=1;@(negedge clk);sret=0;
    privilege=0;trap_cause=6;irq=1;#1;if(vs_vector!=64'h40001014)$fatal(1,"vectored VS timer offset");
    trap_event(6,1,1);privilege=1;
    access(12'h142,0,0,64'h8000000000000005);access(12'h141,0,0,next_pc);
    #1;if(return_priv!=0 || !return_virtual)$fatal(1,"VU return context");
    @(negedge clk);sret=1;@(negedge clk);sret=0;privilege=0;
    access(12'h140,0,0,0,22);access(12'h600,0,0,0,22);
    trap_event(21,1,0,1);privilege=1;
    #1;if(virtual_mode || !hstatus[7] || hstatus[8] || !hstatus[6])$fatal(1,"HS guest trap context");
    access(12'h643,0,0,gpa>>2);access(12'h64a,0,0,64'h3000);
    access(12'h240,0,0,64'hfedcba9876543210);
    mstatus[8]=0;#1;if(return_priv!=0 || !return_virtual || return_pc!=hs_pc)$fatal(1,"HS SRET VU context");
    @(negedge clk);sret=1;@(negedge clk);sret=0;privilege=0;
    trap_event(20,0,0,1);privilege=3;
    #1;if(virtual_mode || !mpv || !gva || mtval2!=(gpa>>2) || mtinst!=64'h3000)$fatal(1,"M guest trap metadata");
    mstatus[12:11]=3;is_mret=1;#1;if(return_virtual)$fatal(1,"MRET M must ignore MPV");
    @(negedge clk);mret=1;@(negedge clk);mret=0;is_mret=0;
    #1;if(virtual_mode || mpv)$fatal(1,"MRET clears MPV");
    trap_event(2,0,0,0,0);#1;if(mtval2 || mtinst || gva)$fatal(1,"ordinary M trap clears guest metadata");
    privilege=1;
    access(12'h605,1,64'hfffffffffffffff6,0); // -10, wraparound guest time
    mtime=100;access(12'h24d,1,91,0);#1;if(hip[6])$fatal(1,"early virtual timer");
    mtime=101;#1;if(!hip[6])$fatal(1,"virtual timer missing");
    access(12'h24d,1,1000,0);#1;if(hip[6])$fatal(1,"virtual timer failed to clear");
    mcounteren=0;access(12'h24d,0,0,0,2);mcounteren=7;
    enter_guest();
    for (int guest_priv = 0; guest_priv < 2; guest_priv++) begin
      privilege=2'(guest_priv);
      for (int gates = 0; gates < 4; gates++) begin
        mcounteren[1]=gates[0];menvcfg[63]=gates[1];
        access(12'h24d,0,0,0,gates==3 ? 22 : 2);
        access(12'h24d,1,42,0,gates==3 ? 22 : 2);
        access(12'h14d,0,0,1000,gates==3 ? (guest_priv==1 ? 0 : 22) : 2);
      end
    end
    access(12'h14d,0,0,1000);
    trap_event(2,1,0,0,0);privilege=1; // hedeleg.2 delegates, still VS
    trap_event(22,1,0,0,0);privilege=1; // virtual instruction cannot delegate to VS
    access(12'h600,1,64'h100080,0); // VTVM plus preserved SPV for HS SRET
    mstatus[8]=1;@(negedge clk);sret=1;@(negedge clk);sret=0;
    access(12'h180,0,0,0,22); // VTVM causes virtual instruction for satp
    $display("PASS rv_hypervisor_csrs_tb checks=%0d guest CSR/trap/return/timer state",checks);$finish;
  end
  initial begin #1000000;$fatal(1,"H CSR timeout");end
endmodule
