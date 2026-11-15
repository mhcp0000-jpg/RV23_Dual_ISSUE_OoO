module rv_hypervisor_decode_tb;
  import rv_hypervisor_decode_pkg::*;
  logic [31:0] instruction;
  hypervisor_decode_t decoded;
  hypervisor_permission_t permission;
  int fd,fields,count=0,xlen,has_inval,priv,virtual_mode,hu,tvm;
  logic [12:0] expected;
  logic expected_exception;
  logic [5:0] expected_cause;
  string path;
  initial begin
    if(!$value$plusargs("vectors=%s",path))$fatal(1,"missing vectors");
    fd=$fopen(path,"r");if(fd==0)$fatal(1,"cannot open vectors");
    while(!$feof(fd))begin
      fields=$fscanf(fd,"%h %d %d %d %d %d %d %h %h %h\n",instruction,xlen,has_inval,priv,virtual_mode,hu,tvm,expected,expected_exception,expected_cause);
      if(fields!=10)$fatal(1,"bad vector %0d",count);
      decoded=decode_hypervisor(instruction,xlen,1'(has_inval));
      permission=hypervisor_permission(decoded,2'(priv),1'(virtual_mode),1'(hu),1'(tvm));
      if(decoded!==expected || permission.exception!==expected_exception || permission.cause!==expected_cause)
        $fatal(1,"H decode %0d insn%h xlen%0d got%h/%h expected%h/%0d/%0d",count,instruction,xlen,decoded,permission,expected,expected_exception,expected_cause);
      count++;
    end
    $display("PASS rv_hypervisor_decode_tb encoding/permission vectors=%0d",count);$finish;
  end
endmodule
