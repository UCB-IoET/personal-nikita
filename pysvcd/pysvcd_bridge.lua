--[[
This code turns a Firestorm into a bridge/adaptor that pysvcd can use over
serial to perform SVCD tasks.

Technically the storms are globally routable and can be accessed over UDP from
Python but that
    a) requires a border router
    b) takes more effort to write because Python typically uses blocking socket
       APIs (instead of event-driven APIs)
]]--


require "cord"
require "svcd"
-- sh = require "stormsh"

print_packed = function(obj)
    -- Print data in a format the python endpoint can decode
    local packed = storm.mp.pack(obj)
    local val = "PACKED<"
    for i = 1, #packed do
        local c = packed:byte(i)
        val = val .. string.format("%02x", c)
    end
    val = val .. ">"
    print(val)
end

-- This instance of svcd is for listening only
SVCD.init(nil, function()
			   end)

SVCD.advert_received = function(pay, srcip, srcport)
    local event = {
        name = "advert_received",
        pay = pay,
        srcip = srcip,
        srcport = srcport,
    }
    print_packed(event)
end

exec_packed = function(obj)
    local unpacked = storm.mp.unpack(obj)
    if unpacked ~= nil then
        if unpacked.name == "SVCD.write" then
            SVCD.write(unpacked.targetip,
                       unpacked.svcid,
                       unpacked.attrid,
                       unpacked.payload,
                       unpacked.timeout_ms,
                       function(code)
                           local event = {
                               name = "write_done",
                               callback_id = unpacked.callback_id,
                               code = code
                           }
                           print_packed(event)
                       end)
        elseif unpacked.name == "SVCD.subscribe" then
            ivkid = SVCD.subscribe(unpacked.targetip,
                                   unpacked.svcid,
                                   unpacked.attrid,
                                   function(val)
                                       local event = {
                                           name = "notify",
                                           ivkid = ivkid,
                                           val = val
                                       }
                                       print_packed(event)
                                   end)
            local eventb = {
                name = "subscribed",
                callback_id = unpacked.callback_id,
                ivkid = ivkid
            }
            print_packed(eventb)
        elseif unpacked.name == "SVCD.unsubscribe" then
            SVCD.unsubscribe(unpacked.targetip,
                             unpacked.svcid,
                             unpacked.attrid,
                             unpacked.ivkid)

        elseif unpacked.name == "ping" then
            unpacked.name = "pong"
            print_packed(unpacked)
        end

    end
end

-- start a coroutine that provides a REPL
-- sh.start()

-- cord.new(function()
-- 			io.write("\n\27[34;1mstormsh> \27[0m")
--             while true do
-- 			   local txt = cord.await(storm.os.read_stdin)
-- 			   storm.os.stormshell(txt)
--             end
-- 		 end)

cord.new(function()
			local packed = ""
            while true do
			   local txt = cord.await(storm.os.read_stdin)
			   packed = packed .. txt
			   local found, found_end = string.find(packed, "SUBMIT")
			   if found ~= nil and found > 1 then
				  exec_packed(string.sub(packed, 1, found - 1))
				  packed = ""
			   end
            end
		 end)


-- enter the main event loop. This puts the processor to sleep
-- in between events
cord.enter_loop()
