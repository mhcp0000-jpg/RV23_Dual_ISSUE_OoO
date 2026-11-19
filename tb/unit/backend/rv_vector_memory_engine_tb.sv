`timescale 1ns/1ps
module rv_vector_memory_engine_tb;
  logic clk=0;always #5 clk=~clk;
  logic rst_n=0,request=0,ready,response,response_ready=0,exception,csr_write=0;
  logic [31:0] instruction=0;
  logic [63:0] a=0,b=0,result,csr_data=0,vl,vtype,vstart,tval;
  logic [11:0] csr_address=0;
  logic [1:0] rm;
  logic sat,dirty;
  logic [5:0] cause;
  logic [4:0] flags;
  logic mem_valid,mem_ready,mem_write,mem_response=0,mem_response_ready;
  logic [31:0] mem_address;
  logic [63:0] mem_data,mem_rdata=0;
  logic [7:0] mem_strobe;
  logic [2:0] mem_size;
  logic ptw_valid,ptw_ready,ptw_response=0,ptw_response_ready;
  logic [55:0] ptw_address;
  logic [63:0] ptw_data=0,satp=0,menvcfg=0;
  rv_ooo_pkg::privilege_e privilege=rv_ooo_pkg::PRIV_M;
  logic [7:0][7:0] pmpcfg=0;
  logic [7:0][61:0] pmpaddr=0;
  logic invalidate=0;
  byte unsigned memory[1048576];
  int cycle=0,delay_q=0,accesses=0;
  int coalesced_reads=0,coalesced_checkpoint=0;
  logic [63:0] expected,expected_tval;
  int fd,fields,count=0,kind,expected_exception,expected_cause;
  string path;
  assign mem_ready=!mem_response && delay_q==0 && cycle%3!=0;
  assign ptw_ready=!ptw_response && cycle%3!=1;
  rv_vector_engine #(.HAS_MMU(1)) dut(.clk_i(clk),.rst_ni(rst_n),.request_valid_i(request),.request_ready_o(ready),
    // This stream covers Bare and nonvirtual S Sv39. Tie authority explicitly:
    // nested default input aliases in Verilator can otherwise inherit the
    // guest helper's virtual=1 default when the owner input is omitted.
    .virtual_i(1'b0),.vsatp_i(64'b0),.hgatp_i(64'b0),.hs_mxr_i(1'b0),
    .guest_pbmt_enable_i(1'b0),.pmm_i(2'b0),
    .instruction_i(instruction),.scalar_a_i(a),.scalar_b_i(b),
    .response_valid_o(response),.response_ready_i(response_ready),.response_flags_o(flags),
    .response_data_o(result),.response_exception_o(exception),.response_cause_o(cause),.response_tval_o(tval),
    .csr_write_i(csr_write),.csr_address_i(csr_address),.csr_data_i(csr_data),
    .vl_o(vl),.vtype_o(vtype),.vstart_o(vstart),.vxrm_o(rm),.vxsat_o(sat),.state_dirty_o(dirty),
    .memory_valid_o(mem_valid),.memory_ready_i(mem_ready),.memory_write_o(mem_write),
    .memory_size_o(mem_size),.memory_address_o(mem_address),.memory_data_o(mem_data),.memory_strobe_o(mem_strobe),
    .memory_response_valid_i(mem_response),.memory_response_ready_o(mem_response_ready),
    .memory_response_data_i(mem_rdata),.invalidate_i(invalidate),.privilege_i(privilege),.satp_i(satp),.menvcfg_i(menvcfg),.pmpcfg_i(pmpcfg),.pmpaddr_i(pmpaddr),
    .ptw_valid_o(ptw_valid),.ptw_ready_i(ptw_ready),.ptw_address_o(ptw_address),
    .ptw_response_valid_i(ptw_response),.ptw_response_ready_o(ptw_response_ready),.ptw_data_i(ptw_data));
  always @(posedge clk)begin
    if(!rst_n)begin cycle<=0;delay_q<=0;mem_response<=0;end
    else begin
      cycle<=cycle+1;
      if(ptw_response && ptw_response_ready)ptw_response<=0;
      if(ptw_valid && ptw_ready)begin
        if(ptw_address<56'h80000000 || ptw_address>=56'h80100000)$fatal(1,"invalid PTW address");
        for(int lane=0;lane<8;lane++)ptw_data[lane*8+:8]<=memory[ptw_address[19:0]+20'(lane)];
        ptw_response<=1;
      end
      if(mem_response && mem_response_ready)mem_response<=0;
      if(delay_q>0)begin
        delay_q<=delay_q-1;
        if(delay_q==1)mem_response<=1;
      end
      if(mem_valid && mem_ready)begin
        if(dut.u_memory.coalesced_q)coalesced_reads++;
        if(mem_address<32'h80000000 || mem_address>=32'h80100000)$fatal(1,"out of SRAM");
        if(mem_strobe!==8'(((9'b1<<(1<<mem_size))-1)<<mem_address[2:0]))$fatal(1,"invalid element strobe");
        if((mem_address & ((32'b1<<mem_size)-1))!=0)$fatal(1,"unaligned physical element");
        for(int lane=0;lane<8;lane++)begin
          mem_rdata[lane*8+:8]<=memory[(mem_address&32'hffff8)+32'(lane)];
          if(mem_write && mem_strobe[lane])memory[(mem_address&32'hffff8)+32'(lane)]<=mem_data[lane*8+:8];
        end
        delay_q<=2+cycle%3;accesses<=accesses+(1<<mem_size);
      end
    end
  end
  initial begin
    for(int i=0;i<1048576;i++)memory[i]=8'(i*37+11);
    if(!$value$plusargs("vectors=%s",path))$fatal(1,"missing vectors");
    fd=$fopen(path,"r");if(!fd)$fatal(1,"cannot open vectors");
    repeat(3)@(negedge clk);rst_n=1;
    while(!$feof(fd))begin
      fields=$fscanf(fd,"%h %h %h %h %h %h %h %h\n",kind,instruction,a,b,expected,expected_exception,expected_cause,expected_tval);
      if(fields!=8)$fatal(1,"bad packet %0d fields%0d",count,fields);
      case(kind)
        1:begin csr_address=instruction[11:0];csr_data=a;csr_write=1;@(negedge clk);csr_write=0;end
        2:memory[a[19:0]]=b[7:0];
        3:if(memory[a[19:0]]!==expected[7:0])$fatal(1,"memory packet%0d address%h got%h expected%h",count,a,memory[a[19:0]],expected[7:0]);
        4:if(vl!==a || vstart!==b)$fatal(1,"state packet%0d vl/start %0d/%0d expected%0d/%0d",count,vl,vstart,a,b);
        5:if(accesses!==int'(a))$fatal(1,"traffic packet%0d got%0d expected%0d",count,accesses,a);
        6:begin
          privilege=rv_ooo_pkg::privilege_e'(instruction[1:0]);satp=a;menvcfg=b;
          pmpcfg[0]=8'h1f;pmpaddr[0]='1;
        end
        7:for(int lane=0;lane<8;lane++)memory[a[19:0]+20'(lane)]=b[lane*8+:8];
        8:begin invalidate=1;@(negedge clk);invalidate=0;end
        9:begin pmpcfg[instruction[2:0]]=a[7:0];pmpaddr[instruction[2:0]]=b[61:0];end
        10:begin
          if(b[0])coalesced_checkpoint=coalesced_reads;
          else if(coalesced_reads-coalesced_checkpoint!=int'(a))
            $fatal(1,"coalesced read count packet%0d got%0d expected%0d",count,coalesced_reads-coalesced_checkpoint,a);
        end
        default:begin
          request=1;do @(posedge clk);while(!ready);
          @(negedge clk);request=0;wait(response);#1;
          if(exception!==1'(expected_exception) || (!exception && (result!==expected || flags!==0)) ||
             (exception && (cause!==6'(expected_cause) || tval!==expected_tval)))begin
            $display("MEM_FAULT_DEBUG priv=%0d virtual=%0d satp=%h translated=%h pmp=%0d sram=%0d trans_fault=%0d trans_cause=%0d pbmt=%0d",privilege,dut.virtual_i,satp,
              dut.u_memory.translated_q,dut.u_memory.pmp_allow,dut.u_memory.physical_sram,dut.u_memory.trans_fault,dut.u_memory.trans_cause,dut.u_memory.translated_pbmt_q);
            $fatal(1,"vector memory packet%0d insn%h data%h exception%0d cause%0d tval%h expected %h/%0d/%0d/%h",
              count,instruction,result,exception,cause,tval,expected,expected_exception,expected_cause,expected_tval);
          end
          repeat(3)@(negedge clk);response_ready=1;@(negedge clk);response_ready=0;
        end
      endcase
      count++;@(negedge clk);
    end
    $display("PASS rv_vector_memory_engine_tb packets=%0d byte accesses=%0d",count,accesses);$finish;
  end
  initial begin #30000000;$fatal(1,"vector memory timeout packet%0d",count);end
endmodule
