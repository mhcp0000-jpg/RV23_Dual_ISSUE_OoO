`timescale 1ns/1ps
module rv23_mmu_tb;
  logic clk=0,rst=0;
  always #5 clk=~clk;
  logic req_valid=0,req_ready,rsp_valid,rsp_ready=0;
  logic [63:0] address=0,satp=0,vsatp=0,hgatp=0,tval,gpa;
  logic [1:0] access_kind=1,privilege=1,pbmt;
  logic virtual_mode=0,sum=0,mxr=0,hs_mxr=0,pbmte=1,guest_pbmte=1;
  logic [31:0] pa;
  logic fault,implicit_access;
  logic [5:0] cause;
  logic mem_valid,mem_ready,mem_rsp_valid=0,mem_rsp_ready,mem_error=0;
  logic [55:0] mem_address;
  logic [63:0] mem_data=0;
  logic [63:0] table_mem[0:8191];
  int cycle=0,reads=0,checks=0,before_reads;
  logic inject_error=0;
  rv23_mmu dut (
    .clk_i(clk),.rst_ni(rst),.req_valid_i(req_valid),.req_ready_o(req_ready),
    .req_address_i(address),.req_access_i(access_kind),.req_privilege_i(privilege),
    .req_virtual_i(virtual_mode),.req_sum_i(sum),.req_mxr_i(mxr),.req_hs_mxr_i(hs_mxr),
    .req_pbmt_enable_i(pbmte),.req_guest_pbmt_enable_i(guest_pbmte),.satp_i(satp),.vsatp_i(vsatp),.hgatp_i(hgatp),
    .rsp_valid_o(rsp_valid),.rsp_ready_i(rsp_ready),.rsp_address_o(pa),.rsp_pbmt_o(pbmt),
    .rsp_fault_o(fault),.rsp_cause_o(cause),.rsp_tval_o(tval),.rsp_guest_address_o(gpa),
    .rsp_implicit_guest_access_o(implicit_access),.mem_valid_o(mem_valid),.mem_ready_i(mem_ready),
    .mem_address_o(mem_address),.mem_response_valid_i(mem_rsp_valid),.mem_response_ready_o(mem_rsp_ready),
    .mem_response_data_i(mem_data),.mem_response_error_i(mem_error));
  assign mem_ready=rst && !mem_rsp_valid && cycle%4!=0;
  always @(posedge clk) begin
    cycle<=cycle+1;
    if(!rst) begin mem_rsp_valid<=0;mem_data<=0;mem_error<=0;end
    else begin
      if(mem_rsp_valid && mem_rsp_ready) mem_rsp_valid<=0;
      if(mem_valid && mem_ready) begin
        reads<=reads+1;mem_rsp_valid<=1;
        mem_error<=inject_error || mem_address[55:16]!=40'h0000008000;
        mem_data<=table_mem[mem_address[15:3]];
      end
    end
  end
  function automatic logic [63:0] pte(input logic [55:0] base,input logic [7:0] flags);
    return (64'(base>>12)<<10)|64'(flags);
  endfunction
  task automatic put(input logic [31:0] location,input logic [63:0] data);
    table_mem[location[15:3]]=data;
  endtask
  task automatic check(input logic [63:0] va,input logic [1:0] kind,input logic [1:0] mode,
      input int expected_cause,input logic [31:0] expected_pa=0,input logic [1:0] expected_pbmt=0,
      input bit expected_implicit=0,input logic [63:0] expected_gpa=0);
    @(negedge clk);address=va;access_kind=kind;privilege=mode;req_valid=1;
    do @(posedge clk);while(!req_ready);
    @(negedge clk);req_valid=0;
    do @(negedge clk);while(!rsp_valid);
    repeat(4) begin
      if(fault!==(expected_cause!=0) || (fault && cause!==6'(expected_cause)) || tval!==va ||
         (!fault && (pa!==expected_pa || pbmt!==expected_pbmt)) ||
         (fault && implicit_access!==expected_implicit) ||
         ((expected_implicit || expected_gpa!=0) && gpa!==expected_gpa))
        $fatal(1,"MMU va=%h kind=%d got PA=%h fault=%b/%d PBMT=%d implicit=%b GPA=%h expected cause=%d PA=%h",
          va,kind,pa,fault,cause,pbmt,implicit_access,gpa,expected_cause,expected_pa);
      @(negedge clk);
    end
    rsp_ready=1;@(negedge clk);rsp_ready=0;checks++;
  endtask
  task automatic clear_tables;
    for(int i=0;i<8192;i++) table_mem[i]=0;
  endtask
  initial begin
    clear_tables();repeat(4) @(negedge clk);rst=1;
    check(64'h80001234,1,3,0,32'h80001234);
    check(64'h100000000,1,3,5);
    satp=64'h8000000000080000;
    put(32'h80000008,pte(56'h80001000,8'h01));
    put(32'h80001000,pte(56'h80002000,8'h01));
    put(32'h80002018,pte(56'h90004000,8'hcf));
    before_reads=reads;check(64'h40003004,1,1,0,32'h90004004);
    if(reads-before_reads!=3) $fatal(1,"Sv39 walk depth");
    check(64'h40003004,0,1,0,32'h90004004);
    check(64'h40003004,2,1,0,32'h90004004);
    check(64'h40003004,1,0,13);
    check(64'h0000010040003004,1,1,13);
    put(32'h80002018,pte(56'h90004000,8'h0f));check(64'h40003004,1,1,13); // A=0
    put(32'h80002018,pte(56'h90004000,8'h4f));check(64'h40003004,2,1,15); // D=0
    put(32'h80002018,pte(56'h90004000,8'h59)); // user execute-only, A=1
    sum=1;mxr=1;check(64'h40003004,1,1,0,32'h90004004);
    check(64'h40003004,3,1,0,32'h90004004); // HLVX uses X, load/SUM privilege
    check(64'h40003004,0,1,12);sum=0;check(64'h40003004,1,1,13);
    check(64'h40003004,0,0,0,32'h90004004);mxr=0;check(64'h40003004,1,0,13);
    check(64'h40003004,3,0,0,32'h90004004);
    check(64'h40003004,3,1,13); // S load from U page still needs SUM
    put(32'h80002018,pte(56'h90004000,8'h53));sum=1;mxr=1;
    check(64'h40003004,3,1,13); // R without X is insufficient despite MXR
    sum=0;mxr=0;
    put(32'h80002018,pte(56'h90004000,8'hcf)|(64'd1<<61));
    check(64'h40003004,1,1,0,32'h90004004,1);pbmte=0;check(64'h40003004,1,1,13);pbmte=1;
    put(32'h80002018,pte(56'h90004000,8'hcf)|(64'd2<<61));check(64'h40003004,1,1,0,32'h90004004,2);
    put(32'h80002018,pte(56'h90004000,8'hcf)|(64'd3<<61));check(64'h40003004,1,1,13);
    put(32'h80002018,pte(56'h90004000,8'hcf)|(64'd1<<54));check(64'h40003004,1,1,13);
    put(32'h80001000,pte(56'h90000000,8'hcf));check(64'h40003004,1,1,0,32'h90003004);
    put(32'h80001000,pte(56'h90001000,8'hcf));check(64'h40003004,1,1,13);
    put(32'h80000008,pte(56'hc0000000,8'hcf));check(64'h40003004,1,1,0,32'hc0003004);
    put(32'h80000008,pte(56'h80001000,8'h41));check(64'h40003004,1,1,13); // nonleaf A forbidden
    put(32'h80000008,pte(56'h80001000,8'h01));put(32'h80001000,pte(56'h80002000,8'h01));
    put(32'h80002058,pte(56'h90018000,8'hcf)|(64'd1<<63));check(64'h4000b004,1,1,0,32'h9001b004);
    put(32'h80002058,pte(56'h90014000,8'hcf)|(64'd1<<63));check(64'h4000b004,1,1,13);
    // Replicate a 64 KiB NAPOT PTE at all sixteen S-stage indices.
    for (int index=0;index<16;index++) begin
      put(32'h80002080+index*8,pte(56'h90028000,8'hcf)|(64'd1<<63));
      check(64'h40010008+(64'(index)<<12),1,1,0,32'h90020008+(32'(index)<<12));
    end
    inject_error=1;check(64'h40003004,1,1,5);inject_error=0;
    // G-stage translates all three VS page-table reads and the final GPA.
    clear_tables();virtual_mode=1;vsatp=64'h8000000000010000;hgatp=64'h8000000000080000;
    put(32'h80000000,pte(56'h80004000,8'h01));
    put(32'h80004400,pte(56'h80005000,8'h01)); // GPA 0x10000000
    put(32'h80004800,pte(56'h80009000,8'h01)); // GPA 0x20000000
    put(32'h80005000,pte(56'h80006000,8'h53)); // G PTE reads only need R/A/U, not W/D
    put(32'h80005008,pte(56'h80007000,8'h53));
    put(32'h80005010,pte(56'h80008000,8'h53));
    put(32'h80006008,pte(56'h10001000,8'h01));
    put(32'h80007000,pte(56'h10002000,8'h01));
    put(32'h80008018,pte(56'h20000000,8'hcf));
    put(32'h80009000,pte(56'h90000000,8'hdf));
    before_reads=reads;check(64'h40003004,1,1,0,32'h90000004);
    if(reads-before_reads!=15) $fatal(1,"VS PTE reads bypassed G-stage: reads=%d",reads-before_reads);
    check(64'h40003004,2,1,0,32'h90000004);

    // Svade leaf checks use the original fetch/load/store for fault cause.
    put(32'h80008018,pte(56'h20000000,8'h8f)); // VS A=0, D=1
    check(64'h40003004,0,1,12);
    check(64'h40003004,1,1,13);
    check(64'h40003004,2,1,15);
    put(32'h80008018,pte(56'h20000000,8'h4f)); // VS A=1, D=0
    check(64'h40003004,0,1,0,32'h90000004);
    check(64'h40003004,1,1,0,32'h90000004);
    check(64'h40003004,2,1,15);
    put(32'h80008018,pte(56'h20000000,8'hcf));
    put(32'h80009000,pte(56'h90000000,8'h9f)); // final G A=0, D=1
    check(64'h40003004,0,1,20,0,0,0,64'h20000004);
    check(64'h40003004,1,1,21,0,0,0,64'h20000004);
    check(64'h40003004,2,1,23,0,0,0,64'h20000004);
    put(32'h80009000,pte(56'h90000000,8'h5f)); // final G A=1, D=0
    check(64'h40003004,0,1,0,32'h90000004);
    check(64'h40003004,1,1,0,32'h90000004);
    check(64'h40003004,2,1,23,0,0,0,64'h20000004);
    put(32'h80009000,pte(56'h90000000,8'hdf));

    // A=0 on the first implicit VS PTE read identifies the PTE's GPA.
    // Restoring R/U/A alone also permits a page walk for an original store.
    put(32'h80005000,pte(56'h80006000,8'h13));
    check(64'h40003004,0,1,20,0,0,1,64'h10000008);
    check(64'h40003004,1,1,21,0,0,1,64'h10000008);
    check(64'h40003004,2,1,23,0,0,1,64'h10000008);
    put(32'h80005000,pte(56'h80006000,8'h53));
    check(64'h40003004,2,1,0,32'h90000004);

    put(32'h80008018,pte(56'h20000000,8'h49));
    put(32'h80009000,pte(56'h90000000,8'h59));
    check(64'h40003004,3,1,0,32'h90000004); // X-only at both stages
    check(64'h40003004,1,1,13);hs_mxr=1;
    check(64'h40003004,1,1,0,32'h90000004); // HS MXR affects both stages
    put(32'h80009000,pte(56'h90000000,8'h53));
    check(64'h40003004,3,1,21,0,0,0,64'h20000004); // G-stage R is not X
    hs_mxr=0;put(32'h80008018,pte(56'h20000000,8'hcf));
    put(32'h80009000,pte(56'h90000000,8'hdf));
    put(32'h80005000,pte(56'h80006000,8'h43));
    check(64'h40003004,1,1,21,0,0,1,64'h10000008);
    put(32'h80005000,pte(56'h80006000,8'h53));
    put(32'h80009000,pte(56'h90000000,8'hcf));check(64'h40003004,1,1,21);
    put(32'h80009000,pte(56'h90000000,8'hdf)|(64'd2<<61));check(64'h40003004,1,1,0,32'h90000004,2);
    // G-stage overrides the PMA first. A nonzero VS-stage PBMT then wins.
    for (int vs_type=0;vs_type<3;vs_type++) begin
      for (int g_type=0;g_type<3;g_type++) begin
        put(32'h80008018,pte(56'h20000000,8'hcf)|(64'(vs_type)<<61));
        put(32'h80009000,pte(56'h90000000,8'hdf)|(64'(g_type)<<61));
        check(64'h40003004,1,1,0,32'h90000004,2'(vs_type!=0 ? vs_type:g_type));
      end
    end
    guest_pbmte=0;check(64'h40003004,1,1,13);guest_pbmte=1;
    put(32'h80008018,pte(56'h20000000,8'hcf));
    pbmte=0;check(64'h40003004,1,1,21,0,0,0,64'h20000004);pbmte=1;

    // A NAPOT leaf in each stage must preserve all four VPN bits.
    for (int index=0;index<16;index++) begin
      put(32'h80008080+index*8,pte(56'h20018000,8'hcf)|(64'd1<<63));
      put(32'h80009080+index*8,pte(56'h90018000,8'hdf)|(64'd1<<63));
    end
    for (int index=0;index<16;index++)
      check(64'h40010008+(64'(index)<<12),1,1,0,32'h90010008+(32'(index)<<12),
        0,0,64'h20010008+(64'(index)<<12));
    put(32'h80008100,pte(56'h20024000,8'hcf)|(64'd1<<63));
    check(64'h40020008,1,1,13); // reserved VS NAPOT PPN encoding
    put(32'h80008100,pte(56'h20020000,8'hcf));
    put(32'h80009100,pte(56'h90024000,8'hdf)|(64'd1<<63));
    check(64'h40020008,1,1,21,0,0,0,64'h20020008); // reserved G NAPOT PPN
    vsatp=0;check(64'h20000004,1,1,0,32'h90000004,2);
    check(64'h0000040020000004,1,1,21);
    hgatp=64'h8000000000080001;check(64'h20000004,1,1,21);
    $display("PASS rv23_mmu_tb checks=%0d Sv39/Svade/PBMT/NAPOT/Sv39x4/implicit-PTE/faults",checks);$finish;
  end
  initial begin #1000000;$fatal(1,"MMU watchdog state=%d",dut.state_q);end
endmodule
