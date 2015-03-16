require "cord" -- scheduler / fiber library
require "storm"

n = 16
blue = storm.array.create(3 * n, storm.array.UINT8)
offish = storm.array.create(3 * n, storm.array.UINT8)

for i = 1,n do
   -- blue
   blue:set(i*3, 0xff)
end


storm.io.set_mode(storm.io.INPUT, storm.io.D3)
storm.io.set_pull(storm.io.PULL_UP, storm.io.D3)

function listen_rising()
   storm.io.watch_single(storm.io.RISING, storm.io.D3, function()
							storm.n.neopixel(blue)
							listen_falling()
													   end)
end

function listen_falling()
   storm.io.watch_single(storm.io.FALLING, storm.io.D3, function()
							storm.n.neopixel(offish)
							listen_rising()
														end)
end

listen_rising()

-- enable a shell
sh = require "stormsh"
sh.start()
cord.enter_loop() -- start event/sleep loop
