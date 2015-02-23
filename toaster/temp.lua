require("storm") -- libraries for interfacing with the board and kernel
require("cord") -- scheduler / fiber library
ADC = require ("adc") -- adc library

----------------------------------------------
-- TEMP class
--   basic TEMP functions associated with a shield pin
--   assume cord.enter_loop() is active, as per stormsh
----------------------------------------------
local TEMP = {}

function TEMP:new()
   local s = ADC:new()
   local active = false
   cord.new(function() 
       rv = s:init() 

	  if (rv ~= 0) then
		 print "Error initializing"
	  else
		 print "Done"
		 active = true
	  end
   end)
   local obj = {}		-- initialize the new object

   obj.temp = 0
   cord.new(function()
      while (active == false) do
         cord.await(storm.os.invokeLater, 250*storm.os.MILLISECOND)
      end
      while(active) do -- FIXME make inactive eventually
         obj.temp = s:get()
         cord.await(storm.os.invokeLater, 250*storm.os.MILLISECOND)
      end
   end)

   setmetatable(obj, self)	-- associate class methods
   self.__index = self
   return obj
end

function TEMP:getTemp()
    return self.temp
   -- temp_constant = 1 --XXX: Figure this out by testing...
   -- return storm.io.get(storm.io[self.pin]) * temp_constant
end

return TEMP
