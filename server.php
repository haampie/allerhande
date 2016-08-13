<?php

function chance() {
    return mt_rand(0, mt_getrandmax() - 1) / mt_getrandmax();
}

function generate(array $markov, string $start, string $max) {
    $words = explode(' ', strtolower($start));
    $output = $words;

    for ($i = 0; $i < $max || $i >= $max && substr(end($words), -1) != '.'; $i++) {
        $key = implode(' ', $words);

        if (false === isset($markov[$key])) {
            return $output;
        }

        $rand = chance();
        $cumulative = 0.0;
        foreach ($markov[$key] as $word => $chance) {
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

$markov = json_decode(file_get_contents('markov.json'), true);

$starts = ['Steek de', 'Rijg de', 'Snijd de', 'Laat de', 'Neem de', 'Roer de'];
$start = $starts[array_rand($starts)];
echo generate($markov, $start, 100);
