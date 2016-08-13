<?php

namespace App\Providers;

use Illuminate\Support\ServiceProvider;

class MarkovGenerator
{
    private $markov;

    public function __construct($markov)
    {
        $this->markov = $markov;
    }

    private function chance()
    {
        return mt_rand(0, mt_getrandmax() - 1) / mt_getrandmax();
    }

    public function __invoke(string $start, string $max)
    {
        $words = explode(' ', strtolower($start));
        $output = $words;

        for ($i = 0; $i < $max || $i >= $max && $i < 2*$max && substr(end($words), -1) != '.'; $i++) {
            $key = implode(' ', $words);

            if (false === isset($this->markov[$key])) {
                return $output;
            }

            $rand = $this->chance();
            $cumulative = 0.0;
            foreach ($this->markov[$key] as $word => $chance) {
                $cumulative += $chance;
                if ($rand <= $cumulative) {
                    $output[] = $word;
                    $words[] = $word;
                    array_shift($words);
                    break;
                }
            }
        }

        return ucfirst(implode(' ', $output));
    }
}

class AppServiceProvider extends ServiceProvider
{
    public function register()
    {
        $this->app->singleton('generator', function () {
            $markov = json_decode(file_get_contents(storage_path('markov-2.json')), true);
            return new MarkovGenerator($markov);
        });
    }
}
