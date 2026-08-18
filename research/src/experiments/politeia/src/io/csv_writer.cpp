#include "io/csv_writer.hpp"

#include <filesystem>
#include <iomanip>
#include <sstream>

namespace politeia {

CSVWriter::CSVWriter(const std::string& output_dir) : output_dir_(output_dir) {
    std::filesystem::create_directories(output_dir);

    energy_file_.open(output_dir + "/energy.csv");
    energy_file_ << "step,time,kinetic,potential_social,potential_terrain,total\n";
    energy_file_ << std::setprecision(12);

    order_file_.open(output_dir + "/order_params.csv");
    order_file_ << "step,time,N,Gini,Q,mean_eps,H,C,F,Psi,"
                   "mean_loyalty,n_attached,Gini_Power\n";
    order_file_ << std::setprecision(8);

    polity_file_.open(output_dir + "/polity_summary.csv");
    polity_file_ << "time,n_polities,n_multi,largest_pop,HHI,mean_pop,"
                    "bands,tribes,chiefdoms,states,empires\n";
    polity_file_ << std::setprecision(6);

    polity_event_file_.open(output_dir + "/polity_events.csv");
    polity_event_file_ << "time,event,polity_gid,other_gid,pop_before,pop_after\n";

    transition_file_.open(output_dir + "/phase_transitions.csv");
    transition_file_ << "time,param,rate,variance,value_before,value_after\n";
    transition_file_ << std::setprecision(8);

    demographics_file_.open(output_dir + "/demographics.csv");
    demographics_file_ << "step,time,N,births,deaths,mean_age,median_age,"
                          "frac_fertile,frac_children,frac_elderly,growth_rate\n";
    demographics_file_ << std::setprecision(6);
}

void CSVWriter::write_snapshot(const ParticleData& particles, Index step,
                               const std::vector<Real>* power) {
    std::ostringstream ss;
    ss << output_dir_ << "/snap_" << std::setw(8) << std::setfill('0')
       << step << ".csv";

    std::ofstream f(ss.str());
    f << "gid,x,y,px,py,w,eps,age,superior,loyalty";

    const int cd = particles.culture_dim();
    for (int d = 0; d < cd; ++d) {
        f << ",c" << d;
    }
    if (power) {
        f << ",power";
    }
    f << "\n";

    f << std::setprecision(8);

    const Real* x = particles.x_data();
    const Real* p = particles.p_data();

    for (Index i = 0; i < particles.count(); ++i) {
        if (particles.status(i) != ParticleStatus::Alive) continue;

        f << particles.global_id(i) << ","
          << x[2*i] << "," << x[2*i+1] << ","
          << p[2*i] << "," << p[2*i+1] << ","
          << particles.wealth(i) << ","
          << particles.epsilon(i) << ","
          << particles.age(i) << ","
          << particles.superior(i) << ","
          << particles.loyalty(i);

        for (int d = 0; d < cd; ++d) {
            f << "," << particles.culture(i, d);
        }

        if (power && i < power->size()) {
            f << "," << (*power)[i];
        }

        f << "\n";
    }
}

void CSVWriter::write_snapshot_binary(const ParticleData& particles, Index step,
                                      const std::vector<Real>* power) {
    std::ostringstream ss;
    ss << output_dir_ << "/snap_" << std::setw(8) << std::setfill('0')
       << step << ".bin";

    std::ofstream f(ss.str(), std::ios::binary);
    if (!f) return;

    const int cd = particles.culture_dim();
    const uint8_t has_power = (power != nullptr) ? 1 : 0;

    Index alive_count = 0;
    for (Index i = 0; i < particles.count(); ++i) {
        if (particles.status(i) == ParticleStatus::Alive) ++alive_count;
    }

    const uint32_t magic = 0x504F4C49; // "POLI"
    const uint16_t version = 1;
    const uint16_t culture_dim_u16 = static_cast<uint16_t>(cd);
    f.write(reinterpret_cast<const char*>(&magic), 4);
    f.write(reinterpret_cast<const char*>(&version), 2);
    f.write(reinterpret_cast<const char*>(&alive_count), sizeof(Index));
    f.write(reinterpret_cast<const char*>(&culture_dim_u16), 2);
    f.write(reinterpret_cast<const char*>(&has_power), 1);

    const Real* x = particles.x_data();
    const Real* p = particles.p_data();

    for (Index i = 0; i < particles.count(); ++i) {
        if (particles.status(i) != ParticleStatus::Alive) continue;

        Id gid = particles.global_id(i);
        Real xi = x[2*i], yi = x[2*i+1];
        Real px = p[2*i], py = p[2*i+1];
        Real w = particles.wealth(i);
        Real eps = particles.epsilon(i);
        Real age = particles.age(i);
        Id sup = particles.superior(i);
        Real loy = particles.loyalty(i);

        f.write(reinterpret_cast<const char*>(&gid), sizeof(Id));
        f.write(reinterpret_cast<const char*>(&xi), sizeof(Real));
        f.write(reinterpret_cast<const char*>(&yi), sizeof(Real));
        f.write(reinterpret_cast<const char*>(&px), sizeof(Real));
        f.write(reinterpret_cast<const char*>(&py), sizeof(Real));
        f.write(reinterpret_cast<const char*>(&w), sizeof(Real));
        f.write(reinterpret_cast<const char*>(&eps), sizeof(Real));
        f.write(reinterpret_cast<const char*>(&age), sizeof(Real));
        f.write(reinterpret_cast<const char*>(&sup), sizeof(Id));
        f.write(reinterpret_cast<const char*>(&loy), sizeof(Real));

        for (int d = 0; d < cd; ++d) {
            Real c = particles.culture(i, d);
            f.write(reinterpret_cast<const char*>(&c), sizeof(Real));
        }

        if (power && i < power->size()) {
            Real pw = (*power)[i];
            f.write(reinterpret_cast<const char*>(&pw), sizeof(Real));
        }
    }
}

void CSVWriter::write_energy(Index step, Real time, Real ke,
                             Real pe_social, Real pe_terrain, Real total) {
    energy_file_ << step << "," << time << ","
                 << ke << "," << pe_social << ","
                 << pe_terrain << "," << total << "\n";
    energy_file_.flush();
}

void CSVWriter::write_order_params(const OrderParams& op) {
    order_file_ << op.step << "," << op.time << ","
                << op.N << "," << op.gini << ","
                << op.Q << "," << op.mean_eps << ","
                << op.H << "," << op.C << ","
                << op.F << "," << op.psi << ","
                << op.mean_loyalty << "," << op.n_attached << ","
                << op.gini_power << "\n";
    order_file_.flush();
}

void CSVWriter::write_polity_summary(const PolitySummary& ps) {
    polity_file_ << ps.time << ","
                 << ps.n_polities << "," << ps.n_multi << ","
                 << ps.largest_pop << "," << ps.hhi << ","
                 << ps.mean_pop << ","
                 << ps.n_bands << "," << ps.n_tribes << ","
                 << ps.n_chiefdoms << "," << ps.n_states << ","
                 << ps.n_empires << "\n";
    polity_file_.flush();
}

void CSVWriter::write_polity_event(const PolityEvent& ev) {
    static const char* names[] = {"formation", "merger", "split", "collapse"};
    polity_event_file_ << ev.time << ","
                       << names[static_cast<int>(ev.type)] << ","
                       << ev.polity_gid << ","
                       << ev.other_gid << ","
                       << ev.pop_before << ","
                       << ev.pop_after << "\n";
    polity_event_file_.flush();
}

void CSVWriter::write_polity_snapshot(
    const std::vector<PolityInfo>& polities, Index step
) {
    std::ostringstream ss;
    ss << output_dir_ << "/polities_" << std::setw(8) << std::setfill('0')
       << step << ".csv";

    std::ofstream f(ss.str());
    f << "root_gid,population,depth,total_wealth,total_power,"
         "mean_loyalty,territory_area,cx,cy,type\n";
    f << std::setprecision(6);

    for (auto& p : polities) {
        f << p.root_gid << ","
          << p.population << ","
          << p.depth << ","
          << p.total_wealth << ","
          << p.total_power << ","
          << p.mean_loyalty << ","
          << p.territory_area << ","
          << p.centroid[0] << ","
          << p.centroid[1] << ","
          << polity_type_name(p.type) << "\n";
    }
}

void CSVWriter::write_transition_event(const TransitionEvent& ev) {
    transition_file_ << ev.time << ","
                     << ev.param_name << ","
                     << ev.rate << ","
                     << ev.variance << ","
                     << ev.value_before << ","
                     << ev.value_after << "\n";
    transition_file_.flush();
}

void CSVWriter::write_demographics(const DemographicRecord& dr) {
    demographics_file_ << dr.step << "," << dr.time << ","
                       << dr.N << "," << dr.births << "," << dr.deaths << ","
                       << dr.mean_age << "," << dr.median_age << ","
                       << dr.frac_fertile << "," << dr.frac_children << ","
                       << dr.frac_elderly << "," << dr.growth_rate << "\n";
    demographics_file_.flush();
}

void CSVWriter::close() {
    if (energy_file_.is_open()) energy_file_.close();
    if (order_file_.is_open()) order_file_.close();
    if (demographics_file_.is_open()) demographics_file_.close();
    if (polity_file_.is_open()) polity_file_.close();
    if (polity_event_file_.is_open()) polity_event_file_.close();
    if (transition_file_.is_open()) transition_file_.close();
}

} // namespace politeia
