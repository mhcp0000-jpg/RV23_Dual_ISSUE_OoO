`timescale 1ns/1ps
module rv23_hypervisor_memory_head_tb;
  import rv_ooo_pkg::*;
  logic clk=0;always #5 clk=~clk;
  logic rst_n=0,req=0,ready,rsp,rsp_ready=0;
  logic [63:0] address=0,operand=0,result,tval;
  logic [2:0] size=0;
  logic write_enable=0,unsign=0,floating=0,exception;
  logic [5:0] cause;
  privilege_e privilege=PRIV_M;
  logic [7:0][7:0] pmpcfg=0;
  logic [7:0][61:0] pmpaddr=0;
  logic mv,mr,mw,mrv=0,mrr,memory_device;
  logic [31:0] ma;
  logic [2:0] memory_size;
  logic execute_permission=0,hs_mxr=0;
  logic coalesce=0,coalesced;
  logic [2:0] coalesce_size=3,coalesced_size;
  logic [1:0] pmm=0;
  logic [63:0] io_word=64'h8877665544332211;
  logic [63:0] md,mrd=0;
  logic [7:0] ms;
  byte unsigned memory[512];
  int ticks=0,accesses=0,checks=0;
  assign mr=!mrv && ticks%3!=0;
  rv23_hypervisor_memory_head #(.HAS_MMU(0),.COALESCE_READ(1)) dut(
    .clk_i(clk),.rst_ni(rst_n),.invalidate_i(1'b0),.execute_permission_i(execute_permission),.pmm_i(pmm),.hs_mxr_i(hs_mxr),
    .request_valid_i(req),.request_ready_o(ready),.address_i(address),.operand_i(operand),
    .size_i(size),.write_i(write_enable),.unsigned_i(unsign),.floating_i(floating),.privilege_i(privilege),
    .coalesce_read_i(coalesce),.response_coalesced_o(coalesced),
    .coalesce_size_i(coalesce_size),.response_coalesced_size_o(coalesced_size),
    .mstatus_i(64'b0),.satp_i(64'b0),.menvcfg_i(64'b0),.senvcfg_i(64'b0),.pmpcfg_i(pmpcfg),.pmpaddr_i(pmpaddr),
    .response_valid_o(rsp),.response_ready_i(rsp_ready),.response_data_o(result),.response_tval_o(tval),
    .response_exception_o(exception),.response_cause_o(cause),
    .ptw_valid_o(),.ptw_device_o(),.ptw_ready_i(1'b0),.ptw_address_o(),
    .ptw_response_valid_i(1'b0),.ptw_response_ready_o(),.ptw_data_i(64'b0),.ptw_error_i(1'b0),
    .memory_valid_o(mv),.memory_ready_i(mr),.memory_write_o(mw),.memory_address_o(ma),.memory_device_o(memory_device),
    .memory_size_o(memory_size),.memory_data_o(md),.memory_strobe_o(ms),.memory_response_valid_i(mrv),.memory_response_ready_o(mrr),
    .memory_response_data_i(mrd),.memory_response_error_i(1'b0));
  always @(posedge clk) begin
    ticks<=ticks+1;
    if(mrv && mrr)mrv<=0;
    if(mv && mr) begin
      if(memory_device!==!ma[31])$fatal(1,"incorrect SRAM/MMIO device attribute");
      if(!(ma>=32'h80000000 && ma<32'h80000200) && !(ma>=32'h02000000 && ma<32'h02000008))$fatal(1,"unexpected memory address %h",ma);
      if(memory_size!=(coalesced?coalesced_size:((address & ((64'b1<<size)-1))==0?size:0)))$fatal(1,"incorrect natural/split size");
      if(ms!==8'(((9'b1<<(1<<memory_size))-1)<<ma[2:0]))$fatal(1,"non-atomic natural strobe");
      accesses<=accesses+1;mrv<=1;
      for(int b=0;b<8;b++) begin
        if(ma[31])begin
          mrd[b*8+:8]<=memory[{ma[8:3],3'b0}+b];
          if(mw && ms[b])memory[{ma[8:3],3'b0}+b]<=md[b*8+:8];
        end else begin
          mrd[b*8+:8]<=io_word[b*8+:8];
          if(mw && ms[b])io_word[b*8+:8]<=md[b*8+:8];
        end
      end
    end
  end
  task automatic transact(input logic[63:0] expected,input bit fault=0,
                          input logic[5:0] fault_cause=0,input logic[63:0] fault_address=0);
    @(negedge clk);req=1;
    do @(posedge clk);while(!ready);
    @(negedge clk);req=0;
    wait(rsp);#1;
    if(exception!==fault || (fault && (cause!==fault_cause || tval!==fault_address)) ||
       (!fault && !write_enable && result!==expected))
      $fatal(1,"assist addr%h size%0d write%0d result%h want%h fault%0d/%0d cause%0d tval%h want%h",
        address,size,write_enable,result,expected,exception,fault,cause,tval,fault_address);
    repeat(4)@(negedge clk);
    rsp_ready=1;@(negedge clk);rsp_ready=0;checks++;
  endtask
  initial begin
    logic [63:0] expected;
    int before_access;
    for(int b=0;b<512;b++)memory[b]=8'(b+128);
    repeat(3)@(negedge clk);rst_n=1;
    for(int s=1;s<=3;s++) for(int offset=1;offset<8;offset++) begin
      if(offset%(1<<s)==0)continue;
      address=64'h80000038+64'(offset);size=3'(s);write_enable=1;
      operand=64'h0123456789abcdef;floating=0;unsign=0;
      transact(0);
      for(int b=0;b<(1<<s);b++)
        if(memory[56+offset+b]!==operand[b*8+:8])$fatal(1,"store data mismatch");
      write_enable=0;
      for(int f=0;f<3;f++) begin
        floating=f==2;unsign=f==1;expected=0;
        for(int b=0;b<(1<<s);b++)expected[b*8+:8]=memory[56+offset+b];
        if(s==1)expected=floating?{48'hffffffffffff,expected[15:0]}:
          (unsign?{48'b0,expected[15:0]}:{{48{expected[15]}},expected[15:0]});
        if(s==2)expected=floating?{32'hffffffff,expected[31:0]}:
          (unsign?{32'b0,expected[31:0]}:{{32{expected[31]}},expected[31:0]});
        transact(expected);
      end
    end
    // Each naturally aligned store/load is ONE complete physical request.
    for(int s=0;s<=3;s++)for(int offset=0;offset<16;offset+=(1<<s))begin
      address=64'h80000100+64'(offset);size=3'(s);write_enable=1;
      operand=64'h8877665544332211;before_access=accesses;
      transact(0);
      if(accesses!=before_access+1)$fatal(1,"naturally aligned store split into multiple transfers");
      write_enable=0;floating=0;unsign=1;expected=0;
      for(int byte_index=0;byte_index<(1<<s);byte_index++)expected[byte_index*8+:8]=memory[256+offset+byte_index];
      transact(expected);
      if(accesses!=before_access+2)$fatal(1,"naturally aligned load split into multiple transfers");
    end
    // Individually permitted bytes cannot combine two PMP entries into a
    // single aligned 64-bit operation. Full-width PMP checking must reject it.
    privilege=PRIV_S;address=64'h80000100;size=3;write_enable=1;
    pmpcfg=0;pmpaddr=0;
    pmpcfg[0]=8'h17;pmpaddr[0]=62'(64'h80000100>>2);
    pmpcfg[1]=8'h17;pmpaddr[1]=62'(64'h80000104>>2);
    before_access=accesses;transact(0,1,7,address);
    if(accesses!=before_access)$fatal(1,"PMP split-entry aligned store escaped");
    write_enable=0;transact(0,1,5,address);
    if(accesses!=before_access)$fatal(1,"PMP split-entry aligned load escaped");
    pmpcfg=0;pmpaddr=0;
    privilege=PRIV_S;pmpaddr[0]=62'(64'h80000040>>2);pmpcfg[0]=8'h0f;
    address=64'h8000003d;size=3;write_enable=1;before_access=accesses;
    transact(0,1,7,64'h80000040);
    if(accesses!=before_access)$fatal(1,"PMP denied split store had side effects");
    privilege=PRIV_M;
    address=64'h800ffffd;before_access=accesses;
    transact(0,1,7,64'h80100000);
    if(accesses!=before_access)$fatal(1,"end-of-SRAM split store had side effects");
    address=64'h02000001;write_enable=0;
    transact(0,1,5,address);
    if(accesses!=before_access)$fatal(1,"MMIO read escaped");
    pmpcfg=0;pmpaddr=0;privilege=PRIV_M;size=2;unsign=1;floating=0;
    address=64'h02000004;write_enable=0;before_access=accesses;
    transact(64'h88776655);
    if(accesses!=before_access+1)$fatal(1,"MMIO load split");
    write_enable=1;operand=64'haabbccdd;transact(0);
    if(io_word!==64'haabbccdd44332211)$fatal(1,"MMIO write data/strobe");
    write_enable=0;execute_permission=1;before_access=accesses;
    transact(0,1,5,address);
    if(accesses!=before_access)$fatal(1,"HLVX executed MMIO");
    address=64'h80000100;size=2;privilege=PRIV_S;
    pmpcfg[0]=8'h14;pmpaddr[0]=62'(address>>2);before_access=accesses;
    transact(0,1,5,address);
    if(accesses!=before_access)$fatal(1,"HLVX bypassed PMP read permission");
    pmpcfg[0]=8'h15;expected=0;
    for(int b=0;b<4;b++)expected[b*8+:8]=memory[256+b];
    transact(expected);
    pmpcfg=0;pmpaddr=0;privilege=PRIV_M;execute_permission=0;pmm=2;
    address=64'hfe00000080000100;transact(expected);
    hs_mxr=1;before_access=accesses;transact(0,1,5,address);
    if(accesses!=before_access)$fatal(1,"HS MXR failed to disable pointer masking");
    hs_mxr=0;execute_permission=1;transact(0,1,5,address);
    // An explicit unit-load opportunity may widen only normal SRAM reads.
    execute_permission=0;pmm=0;coalesce=1;address=64'h80000100;size=2;
    expected=0;for(int b=0;b<8;b++)expected[b*8+:8]=memory[256+b];
    before_access=accesses;transact(expected);
    if(!coalesced || accesses!=before_access+1)$fatal(1,"missing complete SRAM word");
    address=64'h02000000;before_access=accesses;transact({32'b0,io_word[31:0]});
    if(coalesced || accesses!=before_access+1)$fatal(1,"coalesced MMIO side effect");
    address=64'h80000104;expected=0;
    for(int b=0;b<4;b++)expected[b*8+:8]=memory[260+b];
    transact(expected);if(coalesced)$fatal(1,"unaligned word widened");
    address=64'h80000100;privilege=PRIV_S;
    pmpcfg[0]=8'h11;pmpaddr[0]=62'(address>>2);
    pmpcfg[1]=8'h11;pmpaddr[1]=62'((address+4)>>2);
    expected=0;for(int b=0;b<4;b++)expected[b*8+:8]=memory[256+b];
    transact(expected);if(coalesced)$fatal(1,"cross-entry PMP widening");
    size=0;coalesce_size=1;expected=0;
    for(int b=0;b<2;b++)expected[b*8+:8]=memory[256+b];
    transact(expected);if(!coalesced || coalesced_size!=1)$fatal(1,"missing 2-byte group");
    coalesce_size=2;expected=0;
    for(int b=0;b<4;b++)expected[b*8+:8]=memory[256+b];
    transact(expected);if(!coalesced || coalesced_size!=2)$fatal(1,"missing 4-byte group");
    coalesce_size=3;transact(64'(memory[256]));
    if(coalesced)$fatal(1,"8-byte opportunity crossed two PMP entries");
    $display("PASS rv23_hypervisor_memory_head_tb checks=%0d byte_accesses=%0d",checks,accesses);$finish;
  end
  initial begin #1000000;$fatal(1,"assist timeout");end
endmodule
