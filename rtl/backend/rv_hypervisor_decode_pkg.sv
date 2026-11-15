// H/Svinval instruction classification and permissions. Development component;
// misa.H must remain clear until guest state, memory and traps are integrated.
package rv_hypervisor_decode_pkg;
  typedef struct packed {
    logic valid,memory,store,execute_permission,fence,gstage,invalidate;
    logic [1:0] size;
    logic unsigned_load;
    logic [1:0] source_used;
    logic writes_destination;
  } hypervisor_decode_t;
  typedef struct packed {
    logic exception;
    logic [5:0] cause;
  } hypervisor_permission_t;
  function automatic hypervisor_decode_t decode_hypervisor(
    input logic [31:0] instruction,input int xlen=64,input logic has_svinval=1
  );
    hypervisor_decode_t d;
    logic [6:0] funct7;
    logic [4:0] selector;
    d='0;funct7=instruction[31:25];selector=instruction[24:20];
    if(instruction[6:0]==7'h73)begin
      if(instruction[14:12]==0 && instruction[11:7]==0 &&
         funct7 inside {7'h11,7'h31,7'h13,7'h33})begin
        d.valid=!funct7[1] || has_svinval;d.fence=1;
        d.gstage=funct7[5];d.invalidate=funct7[1];d.source_used=3;
      end else if(instruction[14:12]==4)begin
        d.size=instruction[27:26];
        if(funct7 inside {7'h30,7'h32,7'h34,7'h36})begin
          d.valid=(selector==0 || (selector==1 && (d.size!=3) && (xlen==64 || d.size!=2)) ||
            (selector==3 && d.size inside {2'd1,2'd2})) && (xlen==64 || d.size!=3);
          d.execute_permission=selector==3;d.unsigned_load=selector!=0;
          d.writes_destination=instruction[11:7]!=0;d.source_used=1;
        end else if(funct7 inside {7'h31,7'h33,7'h35,7'h37})begin
          d.valid=instruction[11:7]==0 && (xlen==64 || d.size!=3);
          d.store=1;d.source_used=3;
        end
        d.memory=d.valid;
      end
    end
    if(!d.valid)d='0;
    return d;
  endfunction
  function automatic hypervisor_permission_t hypervisor_permission(
    input hypervisor_decode_t decoded,input logic [1:0] privilege,
    input logic virtual_mode,hu,tvm
  );
    hypervisor_permission_t p;
    p='0;p.cause=2;
    if(decoded.valid)begin
      if(virtual_mode)begin p.exception=1;p.cause=22;end
      else if(privilege==0 && !(decoded.memory && hu))p.exception=1;
      else if(privilege==1 && decoded.fence && decoded.gstage && tvm)p.exception=1;
    end
    return p;
  endfunction
  function automatic logic is_hypervisor_fence(input logic [31:0] instruction,
                                               input int xlen=64,input logic has_svinval=1);
    hypervisor_decode_t d;
    d=decode_hypervisor(instruction,xlen,has_svinval);
    return d.valid && d.fence;
  endfunction
endpackage
